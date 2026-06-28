#include "../../cbp.hpp"
#include "../../harcom.hpp"
#include "../common.hpp"

using namespace hcm;

/*
 * TAGE-Lite Line Predictor with Level 1 Helper Table.
 *
 * Pipelining:
 * - Level 1 (predict1): Fast GShare-like lookup of table1_pred (P1 lat = 1).
 *   This matches Level 2's prediction direction in most cases, minimizing short mispredictions.
 * - Level 2 (predict2): Reads base bimodal table (bim) and 2 tagged tables (T1, T2) (P2 lat = 2).
 *   Uses alt-pred redirection and tag matching to override Level 1 if needed.
 *
 * This reduces energy (reading 6 RAMs instead of 9) and increases IPC (minimizing L2 overrides).
 */

template <u64 T0_BITS = 8, u64 L1_BITS = 10, u64 TG_BITS = 8, u64 TAG_B = 8, u64 BHR_B = 10, u64 LINE_B = 4>
struct tageL : predictor
{
    static constexpr u64 T0_ENTRIES = 1 << T0_BITS;
    static constexpr u64 L1_ENTRIES = 1 << L1_BITS;
    static constexpr u64 TG_ENTRIES = 1 << TG_BITS;
    static constexpr u64 LI = 1 << LINE_B; // Number of instructions per line

    // Level 1 Helper Table (2-bit GShare PHT)
    ram<arr<val<2>, LI>, L1_ENTRIES> table1_pred;

    // Level 2 Tables
    ram<arr<val<2>, LI>, T0_ENTRIES> bim; // Base bimodal table

    ram<arr<val<TAG_B>, LI>, TG_ENTRIES> gtag1;
    ram<arr<val<TAG_B>, LI>, TG_ENTRIES> gtag2;

    ram<arr<val<3>, LI>, TG_ENTRIES> gpred1;
    ram<arr<val<3>, LI>, TG_ENTRIES> gpred2;

    ram<arr<val<1>, LI>, TG_ENTRIES> ubit1;
    ram<arr<val<1>, LI>, TG_ENTRIES> ubit2;

    // Folded global history registers for T1 and T2
    global_history<64> gh;
    folded_gh<TG_BITS> t1_idx_fold;
    folded_gh<TAG_B> t1_tag_fold;
    folded_gh<TG_BITS> t2_idx_fold;
    folded_gh<TAG_B> t2_tag_fold;

    // Global History Register (BHR) for L1 lookup and L2 indexing
    reg<BHR_B> bhr;

    // Registers to save prediction state
    reg<L1_BITS> l1_idx;
    arr<reg<2>, LI> reg_l1_ctr_line;
    reg<LI> l1_pred_val_line;

    reg<T0_BITS> bindex;
    arr<reg<2>, LI> reg_b_ctr_line;

    reg<TG_BITS> gindex1;
    reg<TG_BITS> gindex2;

    reg<TAG_B> gtag_calc1;
    reg<TAG_B> gtag_calc2;

    arr<reg<TAG_B>, LI> reg_tag_line1;
    arr<reg<TAG_B>, LI> reg_tag_line2;

    arr<reg<3>, LI> reg_pred_line1;
    arr<reg<3>, LI> reg_pred_line2;

    reg<LI> reg_u_line1;
    reg<LI> reg_u_line2;

    reg<LI> reg_match_line1;
    reg<LI> reg_match_line2;

    reg<LI> reg_final_pred_line;

    // Simulation artifacts to track branches in the block
    u64 num_branches = 0;
    arr<reg<LINE_B>, LI> branch_offset;
    arr<reg<1>, LI> branch_taken;

    val<1> predict1(val<64> inst_pc) override
    {
        num_branches = 0;

        inst_pc.fanout(hard<2> {});

        // Index L1 Helper Table using only PC wires (no XOR logic delay)
        val<L1_BITS> row_idx = val<L1_BITS> { inst_pc >> 6 };
        l1_idx = row_idx;

        arr<val<2>, LI> l1_line = table1_pred.read(row_idx);
        l1_line.fanout(hard<2> {});
        reg_l1_ctr_line = l1_line;

        arr<val<1>, LI> l1_preds = [&](u64 i) {
            return l1_line[i] >> 1;
        };
        l1_preds.fanout(hard<2> {});
        l1_pred_val_line = l1_preds.concat();

        val<LINE_B> offset = inst_pc >> 2;
        offset.fanout(hard<3> {});
        reuse_prediction(offset != hard<LI - 1> {});

        return l1_preds.select(offset);
    }

    val<1> reuse_predict1(val<64> inst_pc) override
    {
        val<LINE_B> offset = inst_pc >> 2;
        offset.fanout(hard<3> {});
        reuse_prediction(offset != hard<LI - 1> {});

        arr<val<1>, LI> pred_line = l1_pred_val_line.make_array(val<1> {});
        return pred_line.select(offset);
    }

    val<1> predict2(val<64> inst_pc) override
    {
        inst_pc.fanout(hard<2> {});

        val<TG_BITS> pc_g = val<TG_BITS> { inst_pc >> 6 };
        pc_g.fanout(hard<3> {});
        val<TAG_B> pc_t = val<TAG_B> { inst_pc >> 6 };
        pc_t.fanout(hard<3> {});

        // 1. Read Base Bimodal Table
        val<T0_BITS> b_idx = val<T0_BITS> { inst_pc >> 6 };
        bindex = b_idx;
        arr<val<2>, LI> b_line = bim.read(b_idx);
        b_line.fanout(hard<2> {});
        reg_b_ctr_line = b_line;

        // 2. Compute indexes and tags for T1 and T2
        val<TG_BITS> idx1 = pc_g ^ t1_idx_fold.get();
        val<TG_BITS> idx2 = pc_g ^ t2_idx_fold.get();
        idx1.fanout(hard<3> {});
        idx2.fanout(hard<3> {});
        gindex1 = idx1;
        gindex2 = idx2;

        val<TAG_B> tag1_calc = pc_t ^ t1_tag_fold.get();
        val<TAG_B> tag2_calc = pc_t ^ t2_tag_fold.get();
        tag1_calc.fanout(hard<2> {});
        tag2_calc.fanout(hard<2> {});
        gtag_calc1 = tag1_calc;
        gtag_calc2 = tag2_calc;

        // 3. Read Tagged Tables
        arr<val<TAG_B>, LI> t_line1 = gtag1.read(idx1);
        arr<val<TAG_B>, LI> t_line2 = gtag2.read(idx2);
        t_line1.fanout(hard<2> {});
        t_line2.fanout(hard<2> {});
        reg_tag_line1 = t_line1;
        reg_tag_line2 = t_line2;

        arr<val<3>, LI> p_line1 = gpred1.read(idx1);
        arr<val<3>, LI> p_line2 = gpred2.read(idx2);
        p_line1.fanout(hard<2> {});
        p_line2.fanout(hard<2> {});
        reg_pred_line1 = p_line1;
        reg_pred_line2 = p_line2;

        arr<val<1>, LI> u_line1 = ubit1.read(idx1);
        arr<val<1>, LI> u_line2 = ubit2.read(idx2);
        u_line1.fanout(hard<2> {});
        u_line2.fanout(hard<2> {});
        reg_u_line1 = u_line1.concat();
        reg_u_line2 = u_line2.concat();

        // Perform matching
        arr<val<1>, LI> m1 = [&](u64 i) { return t_line1[i] == tag1_calc; };
        arr<val<1>, LI> m2 = [&](u64 i) { return t_line2[i] == tag2_calc; };
        m1.fanout(hard<3> {});
        m2.fanout(hard<3> {});
        reg_match_line1 = m1.concat();
        reg_match_line2 = m2.concat();

        // 4. Compute final prediction for each offset in the line
        arr<val<1>, LI> final_pred_line = [&](u64 i) {
            val<1> t0_pred = b_line[i] >> 1;
            val<1> t1_pred = p_line1[i] >> 2;
            val<1> t2_pred = p_line2[i] >> 2;
            
            t0_pred.fanout(hard<3> {});
            t1_pred.fanout(hard<3> {});
            t2_pred.fanout(hard<2> {});

            val<1> m1_i = m1[i];
            val<1> m2_i = m2[i];
            m1_i.fanout(hard<3> {});
            m2_i.fanout(hard<3> {});

            // Alt-Provider prediction
            val<1> ta_pred = select(m1_i, t1_pred, t0_pred);
            ta_pred.fanout(hard<2> {});

            // Provider ID
            val<2> tc_id = select(m2_i, val<2>{2}, select(m1_i, val<2>{1}, val<2>{0}));
            tc_id.fanout(hard<2> {});

            // Provider prediction
            val<1> tc_pred = select(m2_i, t2_pred, select(m1_i, t1_pred, t0_pred));
            tc_pred.fanout(hard<2> {});

            // Weak check
            val<3> tc_ctr = select(m2_i, p_line2[i], select(m1_i, p_line1[i], val<3>{0}));
            tc_ctr.fanout(hard<2> {});
            val<1> is_weak = (tc_ctr == 3) | (tc_ctr == 4);
            is_weak.fanout(hard<2> {});

            val<1> tc_u = select(m2_i, u_line2[i], select(m1_i, u_line1[i], val<1>{0}));
            tc_u.fanout(hard<2> {});

            // Alt redirection
            val<1> is_tagged_prov = (tc_id != 0);
            val<1> use_alt = is_tagged_prov & is_weak & (tc_u == 0);
            use_alt.fanout(hard<2> {});

            return select(use_alt, ta_pred, tc_pred);
        };
        final_pred_line.fanout(hard<2> {});
        reg_final_pred_line = final_pred_line.concat();

        val<LINE_B> offset = inst_pc >> 2;
        offset.fanout(hard<3> {});
        reuse_prediction(offset != hard<LI - 1> {});

        return final_pred_line.select(offset);
    }

    val<1> reuse_predict2(val<64> inst_pc) override
    {
        val<LINE_B> offset = inst_pc >> 2;
        offset.fanout(hard<3> {});
        reuse_prediction(offset != hard<LI - 1> {});

        arr<val<1>, LI> pred_taken = reg_final_pred_line.make_array(val<1> {});
        return pred_taken.select(offset);
    }

    inline val<3> update_counter(val<3> ctr, val<1> incr)
    {
        ctr.fanout(hard<6> {});
        val<3> increased = select(ctr == 7, ctr, val<3> { ctr + 1 });
        val<3> decreased = select(ctr == 0, ctr, val<3> { ctr - 1 });
        return select(incr.fo1(), increased.fo1(), decreased.fo1());
    }

    inline val<2> update_counter_2b(val<2> ctr, val<1> incr)
    {
        ctr.fanout(hard<6> {});
        val<2> increased = select(ctr == 3, ctr, val<2> { ctr + 1 });
        val<2> decreased = select(ctr == 0, ctr, val<2> { ctr - 1 });
        return select(incr.fo1(), increased.fo1(), decreased.fo1());
    }

    void update_condbr(val<64> branch_pc, val<1> taken, [[maybe_unused]] val<64> next_pc) override
    {
        branch_offset[num_branches] = branch_pc >> 2;
        branch_taken[num_branches] = taken;
        num_branches++;
    }

    void update_cycle(instruction_info& block_end_info) override
    {
        val<1>& mispredict = block_end_info.is_mispredict;

        if (num_branches == 0)
        {
            return;
        }

        // 1. Update BHR
        val<LI> new_history = branch_taken.concat().reverse() >> (LI - num_branches);
        new_history.fanout(hard<3> {});
        bhr = (bhr << num_branches) + val<BHR_B> { new_history };
        gh.update(new_history);

        // 2. Build branch mask and taken mask for the cacheline
        mispredict.fanout(hard<2> {});
        branch_offset.fanout(hard<LI> {});
        branch_taken.fanout(hard<3> {});

        arr<val<LI>, LI> branch_onehot = [&](u64 i) {
            val<LI> valid_mask = val<1> { i < num_branches }.replicate(hard<LI> {}).concat();
            return valid_mask & branch_offset[i].decode().concat();
        };
        branch_onehot.fanout(hard<2> {});
        val<LI> branch_mask = branch_onehot.fold_or();
        branch_mask.fanout(hard<4> {});

        arr<val<LI>, LI> taken_onehot = [&](u64 i) {
            return branch_onehot[i] & branch_taken[i].replicate(hard<LI> {}).concat();
        };
        val<LI> taken_mask = taken_onehot.fold_or();
        taken_mask.fanout(hard<3> {});

        // 3. Declare fanouts of captured registers
        reg_match_line1.fanout(hard<2> {});
        reg_match_line2.fanout(hard<2> {});

        reg_u_line1.fanout(hard<2> {});
        reg_u_line2.fanout(hard<2> {});

        reg_final_pred_line.fanout(hard<2> {});

        // 4. Construct updated lines for all components
        // L1 Helper Table (table1_pred) updates unconditionally
        arr<val<2>, LI> new_l1_line = [&](u64 i) {
            val<1> is_exec = val<1> { branch_mask >> i };
            val<1> is_taken = val<1> { taken_mask >> i };
            val<2> updated_ctr = update_counter_2b(reg_l1_ctr_line[i], is_taken);
            return select(is_exec, updated_ctr, reg_l1_ctr_line[i]);
        };
        new_l1_line.fanout(hard<2> {});

        // T0 Base Predictor
        arr<val<2>, LI> new_b_line = [&](u64 i) {
            val<1> is_exec = val<1> { branch_mask >> i };
            val<1> is_taken = val<1> { taken_mask >> i };

            val<1> m1_i = val<1> { reg_match_line1 >> i };
            val<1> m2_i = val<1> { reg_match_line2 >> i };
            val<2> tc_id_i = select(m2_i, val<2>{2}, select(m1_i, val<2>{1}, val<2>{0}));

            val<1> update_b_i = is_exec & (tc_id_i == 0);
            val<2> updated_ctr = update_counter_2b(reg_b_ctr_line[i], is_taken);
            return select(update_b_i, updated_ctr, reg_b_ctr_line[i]);
        };
        new_b_line.fanout(hard<2> {});

        arr<val<3>, LI> new_pred_line1 = [&](u64 i) {
            val<1> is_exec = val<1> { branch_mask >> i };
            val<1> is_taken = val<1> { taken_mask >> i };
            is_taken.fanout(hard<2> {});

            val<1> m1_i = val<1> { reg_match_line1 >> i };
            val<1> m2_i = val<1> { reg_match_line2 >> i };
            m1_i.fanout(hard<3> {});
            m2_i.fanout(hard<3> {});

            val<2> tc_id_i = select(m2_i, val<2>{2}, select(m1_i, val<2>{1}, val<2>{0}));
            tc_id_i.fanout(hard<2> {});

            val<3> tc_ctr_i = select(m2_i, reg_pred_line2[i], select(m1_i, reg_pred_line1[i], val<3>{0}));
            tc_ctr_i.fanout(hard<2> {});
            val<3> new_tc_ctr_i = update_counter(tc_ctr_i, is_taken);
            new_tc_ctr_i.fanout(hard<2> {});

            val<3> init_ctr_i = select(is_taken, val<3>{4}, val<3>{3});
            init_ctr_i.fanout(hard<2> {});

            val<1> final_pred_i = val<1> { reg_final_pred_line >> i };
            val<1> misp_i = is_exec & (final_pred_i != is_taken);
            misp_i.fanout(hard<2> {});

            val<1> tc_lt_1 = (tc_id_i == 0);
            val<1> u1_i = val<1> { reg_u_line1 >> i };
            val<1> alloc1_i = misp_i & tc_lt_1 & (u1_i == 0);

            val<1> update_pred1_i = is_exec & (tc_id_i == 1) & (new_tc_ctr_i != tc_ctr_i);
            val<1> write_pred1_i = update_pred1_i | alloc1_i;
            val<3> new_pred1_val_i = select(alloc1_i, init_ctr_i, new_tc_ctr_i);

            return select(write_pred1_i, new_pred1_val_i, reg_pred_line1[i]);
        };

        arr<val<3>, LI> new_pred_line2 = [&](u64 i) {
            val<1> is_exec = val<1> { branch_mask >> i };
            val<1> is_taken = val<1> { taken_mask >> i };
            is_taken.fanout(hard<2> {});

            val<1> m1_i = val<1> { reg_match_line1 >> i };
            val<1> m2_i = val<1> { reg_match_line2 >> i };
            m1_i.fanout(hard<3> {});
            m2_i.fanout(hard<3> {});

            val<2> tc_id_i = select(m2_i, val<2>{2}, select(m1_i, val<2>{1}, val<2>{0}));
            tc_id_i.fanout(hard<3> {});

            val<3> tc_ctr_i = select(m2_i, reg_pred_line2[i], select(m1_i, reg_pred_line1[i], val<3>{0}));
            tc_ctr_i.fanout(hard<2> {});
            val<3> new_tc_ctr_i = update_counter(tc_ctr_i, is_taken);
            new_tc_ctr_i.fanout(hard<2> {});

            val<3> init_ctr_i = select(is_taken, val<3>{4}, val<3>{3});
            init_ctr_i.fanout(hard<2> {});

            val<1> final_pred_i = val<1> { reg_final_pred_line >> i };
            val<1> misp_i = is_exec & (final_pred_i != is_taken);
            misp_i.fanout(hard<2> {});

            val<1> tc_lt_1 = (tc_id_i == 0);
            val<1> tc_lt_2 = (tc_id_i == 0) | (tc_id_i == 1);
            tc_lt_2.fanout(hard<2> {});

            val<1> u1_i = val<1> { reg_u_line1 >> i };
            val<1> u2_i = val<1> { reg_u_line2 >> i };

            val<1> eligible1_i = misp_i & tc_lt_1 & (u1_i == 0);
            val<1> eligible2_i = misp_i & tc_lt_2 & (u2_i == 0);

            val<1> alloc2_i = ~eligible1_i & eligible2_i;

            val<1> update_pred2_i = is_exec & (tc_id_i == 2) & (new_tc_ctr_i != tc_ctr_i);
            val<1> write_pred2_i = update_pred2_i | alloc2_i;
            val<3> new_pred2_val_i = select(alloc2_i, init_ctr_i, new_tc_ctr_i);

            return select(write_pred2_i, new_pred2_val_i, reg_pred_line2[i]);
        };

        arr<val<1>, LI> new_u_line1 = [&](u64 i) {
            val<1> is_exec = val<1> { branch_mask >> i };
            val<1> is_taken = val<1> { taken_mask >> i };
            is_taken.fanout(hard<2> {});

            val<1> m1_i = val<1> { reg_match_line1 >> i };
            val<1> m2_i = val<1> { reg_match_line2 >> i };
            m1_i.fanout(hard<3> {});
            m2_i.fanout(hard<3> {});

            val<2> tc_id_i = select(m2_i, val<2>{2}, select(m1_i, val<2>{1}, val<2>{0}));
            tc_id_i.fanout(hard<4> {});

            val<1> t0_pred = reg_b_ctr_line[i] >> 1;
            val<1> t1_pred = reg_pred_line1[i] >> 2;
            val<1> t2_pred = reg_pred_line2[i] >> 2;
            t0_pred.fanout(hard<3> {});
            t1_pred.fanout(hard<3> {});
            t2_pred.fanout(hard<2> {});

            val<1> tc_pred_i = select(m2_i, t2_pred, select(m1_i, t1_pred, t0_pred));
            tc_pred_i.fanout(hard<2> {});

            val<1> ta_pred_i = select(m1_i, t1_pred, t0_pred);

            val<1> final_pred_i = val<1> { reg_final_pred_line >> i };
            val<1> misp_i = is_exec & (final_pred_i != is_taken);
            misp_i.fanout(hard<2> {});

            val<1> u1_i = val<1> { reg_u_line1 >> i };
            val<1> u2_i = val<1> { reg_u_line2 >> i };
            u2_i.fanout(hard<2> {});

            val<1> tc_lt_1 = (tc_id_i == 0);
            val<1> eligible1_i = misp_i & tc_lt_1 & (u1_i == 0);
            val<1> alloc1_i = eligible1_i;

            val<1> all_u_1_2_i = (u1_i == 1) & (u2_i == 1);
            val<1> decay1_i = misp_i & tc_lt_1 & all_u_1_2_i;

            val<1> u_cond_i = (tc_pred_i != ta_pred_i);
            val<1> new_u_i = select(tc_pred_i == is_taken, val<1>{1}, val<1>{0});

            val<1> update_u1_i = is_exec & (tc_id_i == 1) & u_cond_i;
            val<1> alloc1_or_decay1_i = alloc1_i | decay1_i;
            val<1> write_u1_i = update_u1_i | alloc1_or_decay1_i;
            val<1> new_u1_val_i = select(alloc1_or_decay1_i, val<1>{0}, new_u_i);

            return select(write_u1_i, new_u1_val_i, u1_i);
        };

        arr<val<1>, LI> new_u_line2 = [&](u64 i) {
            val<1> is_exec = val<1> { branch_mask >> i };
            val<1> is_taken = val<1> { taken_mask >> i };
            is_taken.fanout(hard<2> {});

            val<1> m1_i = val<1> { reg_match_line1 >> i };
            val<1> m2_i = val<1> { reg_match_line2 >> i };
            m1_i.fanout(hard<3> {});
            m2_i.fanout(hard<3> {});

            val<2> tc_id_i = select(m2_i, val<2>{2}, select(m1_i, val<2>{1}, val<2>{0}));
            tc_id_i.fanout(hard<5> {});

            val<1> t0_pred = reg_b_ctr_line[i] >> 1;
            val<1> t1_pred = reg_pred_line1[i] >> 2;
            val<1> t2_pred = reg_pred_line2[i] >> 2;
            t0_pred.fanout(hard<3> {});
            t1_pred.fanout(hard<3> {});
            t2_pred.fanout(hard<2> {});

            val<1> tc_pred_i = select(m2_i, t2_pred, select(m1_i, t1_pred, t0_pred));
            tc_pred_i.fanout(hard<2> {});

            val<1> ta_pred_i = select(m1_i, t1_pred, t0_pred);

            val<1> final_pred_i = val<1> { reg_final_pred_line >> i };
            val<1> misp_i = is_exec & (final_pred_i != is_taken);
            misp_i.fanout(hard<2> {});

            val<1> u1_i = val<1> { reg_u_line1 >> i };
            val<1> u2_i = val<1> { reg_u_line2 >> i };
            u1_i.fanout(hard<2> {});
            u2_i.fanout(hard<2> {});

            val<1> tc_lt_1 = (tc_id_i == 0);
            val<1> tc_lt_2 = (tc_id_i == 0) | (tc_id_i == 1);
            tc_lt_2.fanout(hard<2> {});

            val<1> eligible1_i = misp_i & tc_lt_1 & (u1_i == 0);
            val<1> eligible2_i = misp_i & tc_lt_2 & (u2_i == 0);

            val<1> alloc2_i = ~eligible1_i & eligible2_i;

            val<1> all_u_1_2_i = (u1_i == 1) & (u2_i == 1);

            val<1> decay1_i = misp_i & tc_lt_1 & all_u_1_2_i;
            val<1> decay2_i = select(tc_id_i == 0, decay1_i, misp_i & (tc_id_i == 1) & (u2_i == 1));

            val<1> u_cond_i = (tc_pred_i != ta_pred_i);
            val<1> new_u_i = select(tc_pred_i == is_taken, val<1>{1}, val<1>{0});

            val<1> update_u2_i = is_exec & (tc_id_i == 2) & u_cond_i;
            val<1> alloc2_or_decay2_i = alloc2_i | decay2_i;
            val<1> write_u2_i = update_u2_i | alloc2_or_decay2_i;
            val<1> new_u2_val_i = select(alloc2_or_decay2_i, val<1>{0}, new_u_i);

            return select(write_u2_i, new_u2_val_i, u2_i);
        };

        arr<val<TAG_B>, LI> new_tag_line1 = [&](u64 i) {
            val<1> is_exec = val<1> { branch_mask >> i };
            val<1> is_taken = val<1> { taken_mask >> i };

            val<1> m1_i = val<1> { reg_match_line1 >> i };
            val<1> m2_i = val<1> { reg_match_line2 >> i };
            m1_i.fanout(hard<2> {});
            m2_i.fanout(hard<2> {});

            val<2> tc_id_i = select(m2_i, val<2>{2}, select(m1_i, val<2>{1}, val<2>{0}));

            val<1> final_pred_i = val<1> { reg_final_pred_line >> i };
            val<1> misp_i = is_exec & (final_pred_i != is_taken);

            val<1> tc_lt_1 = (tc_id_i == 0);
            val<1> u1_i = val<1> { reg_u_line1 >> i };
            val<1> alloc1_i = misp_i & tc_lt_1 & (u1_i == 0);

            return select(alloc1_i, gtag_calc1, reg_tag_line1[i]);
        };

        arr<val<TAG_B>, LI> new_tag_line2 = [&](u64 i) {
            val<1> is_exec = val<1> { branch_mask >> i };
            val<1> is_taken = val<1> { taken_mask >> i };

            val<1> m1_i = val<1> { reg_match_line1 >> i };
            val<1> m2_i = val<1> { reg_match_line2 >> i };
            m1_i.fanout(hard<2> {});
            m2_i.fanout(hard<2> {});

            val<2> tc_id_i = select(m2_i, val<2>{2}, select(m1_i, val<2>{1}, val<2>{0}));
            tc_id_i.fanout(hard<2> {});

            val<1> final_pred_i = val<1> { reg_final_pred_line >> i };
            val<1> misp_i = is_exec & (final_pred_i != is_taken);
            misp_i.fanout(hard<2> {});

            val<1> tc_lt_1 = (tc_id_i == 0);
            val<1> tc_lt_2 = (tc_id_i == 0) | (tc_id_i == 1);

            val<1> u1_i = val<1> { reg_u_line1 >> i };
            val<1> u2_i = val<1> { reg_u_line2 >> i };

            val<1> eligible1_i = misp_i & tc_lt_1 & (u1_i == 0);
            val<1> eligible2_i = misp_i & tc_lt_2 & (u2_i == 0);

            val<1> alloc2_i = ~eligible1_i & eligible2_i;

            return select(alloc2_i, gtag_calc2, reg_tag_line2[i]);
        };

        // 5. Determine which updates are actually performed
        val<1> performing_l1_update = (new_l1_line.concat() != reg_l1_ctr_line.concat());
        val<1> performing_b_update = (new_b_line.concat() != reg_b_ctr_line.concat());

        arr<val<1>, LI> pred1_diff = [&](u64 i) { return new_pred_line1[i] != reg_pred_line1[i]; };
        arr<val<1>, LI> pred2_diff = [&](u64 i) { return new_pred_line2[i] != reg_pred_line2[i]; };

        val<1> performing_pred1_update = (pred1_diff.concat() != hard<0> {});
        val<1> performing_pred2_update = (pred2_diff.concat() != hard<0> {});

        val<1> performing_u1_update = (new_u_line1.concat() != reg_u_line1);
        val<1> performing_u2_update = (new_u_line2.concat() != reg_u_line2);

        arr<val<1>, LI> tag1_diff = [&](u64 i) { return new_tag_line1[i] != reg_tag_line1[i]; };
        arr<val<1>, LI> tag2_diff = [&](u64 i) { return new_tag_line2[i] != reg_tag_line2[i]; };

        val<1> performing_tag1_update = (tag1_diff.concat() != hard<0> {});
        val<1> performing_tag2_update = (tag2_diff.concat() != hard<0> {});

        performing_l1_update.fanout(hard<2> {});
        performing_b_update.fanout(hard<2> {});
        performing_pred1_update.fanout(hard<2> {});
        performing_pred2_update.fanout(hard<2> {});

        performing_u1_update.fanout(hard<2> {});
        performing_u2_update.fanout(hard<2> {});

        performing_tag1_update.fanout(hard<2> {});
        performing_tag2_update.fanout(hard<2> {});

        val<1> updates_made = performing_l1_update | performing_b_update | 
                              performing_pred1_update | performing_pred2_update | 
                              performing_u1_update | performing_u2_update | 
                              performing_tag1_update | performing_tag2_update;
        need_extra_cycle(updates_made);

        // 6. Write operations
        execute_if(performing_l1_update, [&]() {
            table1_pred.write(l1_idx, new_l1_line);
        });

        execute_if(performing_b_update, [&]() {
            bim.write(bindex, new_b_line);
        });

        execute_if(performing_pred1_update, [&]() { gpred1.write(gindex1, new_pred_line1); });
        execute_if(performing_pred2_update, [&]() { gpred2.write(gindex2, new_pred_line2); });

        execute_if(performing_u1_update, [&]() { ubit1.write(gindex1, new_u_line1); });
        execute_if(performing_u2_update, [&]() { ubit2.write(gindex2, new_u_line2); });

        execute_if(performing_tag1_update, [&]() { gtag1.write(gindex1, new_tag_line1); });
        execute_if(performing_tag2_update, [&]() { gtag2.write(gindex2, new_tag_line2); });

        num_branches = 0;
    }
};

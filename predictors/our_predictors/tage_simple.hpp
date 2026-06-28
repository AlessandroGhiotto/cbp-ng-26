#include "../../cbp.hpp"
#include "../../harcom.hpp"
#include "../common.hpp"

using namespace hcm;

/*
 * tage_simple - A single-instruction pipelined TAGE-Lite predictor.
 *
 * It uses:
 * - Level 1 (predict1): 1-cycle bimodal table (T0) lookup.
 * - Level 2 (predict2): 2-cycle tagged tables (T1, T2, T3) lookup with geometric history lengths:
 *   L1 = 8, L2 = 24, L3 = 64.
 *
 * This provides high accuracy and low latency (P1 lat = 1, P2 lat = 2).
 */

template <u64 T0_BITS = 10, u64 TG_BITS = 9, u64 TAG_B = 8>
struct tage_simple : predictor
{
    static constexpr u64 T0_ENTRIES = 1 << T0_BITS;
    static constexpr u64 TG_ENTRIES = 1 << TG_BITS;

    // T0 base predictor (tag-less 2-bit counters)
    ram<val<2>, T0_ENTRIES> bim;

    // Tagged tables T1, T2, T3
    ram<val<TAG_B>, TG_ENTRIES> gtag1;
    ram<val<TAG_B>, TG_ENTRIES> gtag2;
    ram<val<TAG_B>, TG_ENTRIES> gtag3;

    ram<val<3>, TG_ENTRIES> gpred1;
    ram<val<3>, TG_ENTRIES> gpred2;
    ram<val<3>, TG_ENTRIES> gpred3;

    ram<val<1>, TG_ENTRIES> ubit1;
    ram<val<1>, TG_ENTRIES> ubit2;
    ram<val<1>, TG_ENTRIES> ubit3;

    // Folded global history registers
    global_history<64> gh;
    folded_gh<TG_BITS> t1_idx_fold;
    folded_gh<TAG_B> t1_tag_fold;
    folded_gh<TG_BITS> t2_idx_fold;
    folded_gh<TAG_B> t2_tag_fold;
    folded_gh<TG_BITS> t3_idx_fold;
    folded_gh<TAG_B> t3_tag_fold;

    // Prediction state registers
    reg<T0_BITS> bindex;
    reg<2> reg_b_ctr;
    reg<1> bpred_val;

    reg<TG_BITS> gindex1;
    reg<TG_BITS> gindex2;
    reg<TG_BITS> gindex3;

    reg<TAG_B> gtag_calc1;
    reg<TAG_B> gtag_calc2;
    reg<TAG_B> gtag_calc3;

    reg<TAG_B> read_tag1;
    reg<TAG_B> read_tag2;
    reg<TAG_B> read_tag3;

    reg<3> read_pred1;
    reg<3> read_pred2;
    reg<3> read_pred3;

    reg<1> read_u1;
    reg<1> read_u2;
    reg<1> read_u3;

    reg<1> reg_match1;
    reg<1> reg_match2;
    reg<1> reg_match3;

    reg<2> reg_tc_id;
    reg<1> reg_tc_pred;
    reg<3> reg_tc_ctr;
    reg<1> alt_pred;
    reg<1> reg_use_alt;
    reg<1> reg_final_pred;

    val<1> predict1(val<64> inst_pc) override
    {
        inst_pc.fanout(hard<2> {});

        // Index T0 base predictor
        val<T0_BITS> b_idx = val<T0_BITS> { inst_pc >> 2 };
        bindex = b_idx;

        val<2> b_ctr = bim.read(b_idx.fo1());
        b_ctr.fanout(hard<2> {});
        reg_b_ctr = b_ctr;

        val<1> bp = b_ctr >> 1;
        bpred_val = bp;

        return bp;
    }

    val<1> reuse_predict1([[maybe_unused]] val<64> inst_pc) override
    {
        return bpred_val;
    }

    val<1> predict2(val<64> inst_pc) override
    {
        inst_pc.fanout(hard<2> {});

        val<TG_BITS> pc_g = val<TG_BITS> { inst_pc >> 2 };
        pc_g.fanout(hard<4> {});
        val<TAG_B> pc_t = val<TAG_B> { inst_pc >> 2 };
        pc_t.fanout(hard<4> {});

        // Compute indexes and tags for T1, T2, T3
        val<TG_BITS> idx1 = pc_g ^ t1_idx_fold.get();
        val<TG_BITS> idx2 = pc_g ^ t2_idx_fold.get();
        val<TG_BITS> idx3 = pc_g ^ t3_idx_fold.get();
        idx1.fanout(hard<3> {});
        idx2.fanout(hard<3> {});
        idx3.fanout(hard<3> {});
        gindex1 = idx1;
        gindex2 = idx2;
        gindex3 = idx3;

        val<TAG_B> tag1_calc = pc_t ^ t1_tag_fold.get();
        val<TAG_B> tag2_calc = pc_t ^ t2_tag_fold.get();
        val<TAG_B> tag3_calc = pc_t ^ t3_tag_fold.get();
        tag1_calc.fanout(hard<2> {});
        tag2_calc.fanout(hard<2> {});
        tag3_calc.fanout(hard<2> {});
        gtag_calc1 = tag1_calc;
        gtag_calc2 = tag2_calc;
        gtag_calc3 = tag3_calc;

        // Read Tagged tables
        val<TAG_B> tag1 = gtag1.read(idx1);
        val<TAG_B> tag2 = gtag2.read(idx2);
        val<TAG_B> tag3 = gtag3.read(idx3);
        tag1.fanout(hard<2> {});
        tag2.fanout(hard<2> {});
        tag3.fanout(hard<2> {});
        read_tag1 = tag1;
        read_tag2 = tag2;
        read_tag3 = tag3;

        val<3> pred1 = gpred1.read(idx1);
        val<3> pred2 = gpred2.read(idx2);
        val<3> pred3 = gpred3.read(idx3);
        pred1.fanout(hard<2> {});
        pred2.fanout(hard<2> {});
        pred3.fanout(hard<2> {});
        read_pred1 = pred1;
        read_pred2 = pred2;
        read_pred3 = pred3;

        val<1> u1 = ubit1.read(idx1);
        val<1> u2 = ubit2.read(idx2);
        val<1> u3 = ubit3.read(idx3);
        u1.fanout(hard<2> {});
        u2.fanout(hard<2> {});
        u3.fanout(hard<2> {});
        read_u1 = u1;
        read_u2 = u2;
        read_u3 = u3;

        // Tag matching
        val<1> m1 = (tag1 == tag1_calc);
        val<1> m2 = (tag2 == tag2_calc);
        val<1> m3 = (tag3 == tag3_calc);
        m1.fanout(hard<4> {});
        m2.fanout(hard<4> {});
        m3.fanout(hard<4> {});
        reg_match1 = m1;
        reg_match2 = m2;
        reg_match3 = m3;

        // Determine predictions
        val<1> t0_pred = bpred_val;
        val<1> t1_pred = pred1 >> 2;
        val<1> t2_pred = pred2 >> 2;
        val<1> t3_pred = pred3 >> 2;
        t0_pred.fanout(hard<4> {});
        t1_pred.fanout(hard<3> {});
        t2_pred.fanout(hard<3> {});
        t3_pred.fanout(hard<2> {});

        // Alt-Provider prediction (ta_pred)
        val<1> alt_if_m3 = select(m2, t2_pred, select(m1, t1_pred, t0_pred));
        val<1> alt_if_m2 = select(m1, t1_pred, t0_pred);
        val<1> ta_pred = select(m3, alt_if_m3, select(m2, alt_if_m2, t0_pred));
        ta_pred.fanout(hard<2> {});
        alt_pred = ta_pred;

        // Provider prediction (tc_pred) & Provider ID (tc_id)
        val<2> tc_id = select(m3, val<2>{3}, select(m2, val<2>{2}, select(m1, val<2>{1}, val<2>{0})));
        tc_id.fanout(hard<2> {});
        reg_tc_id = tc_id;

        val<1> tc_pred = select(m3, t3_pred, select(m2, t2_pred, select(m1, t1_pred, t0_pred)));
        tc_pred.fanout(hard<2> {});
        reg_tc_pred = tc_pred;

        // Weak Provider check
        val<3> tc_ctr = select(m3, pred3, select(m2, pred2, select(m1, pred1, val<3>{0})));
        tc_ctr.fanout(hard<2> {});
        reg_tc_ctr = tc_ctr;

        val<1> is_weak = (tc_ctr == 3) | (tc_ctr == 4);
        is_weak.fanout(hard<2> {});

        val<1> tc_u = select(m3, u3, select(m2, u2, select(m1, u1, val<1>{0})));
        tc_u.fanout(hard<2> {});

        // Alt-pred redirection
        val<1> is_tagged_prov = (tc_id != 0);
        val<1> use_alt = is_tagged_prov & is_weak & (tc_u == 0);
        use_alt.fanout(hard<2> {});
        reg_use_alt = use_alt;

        val<1> final_pred = select(use_alt, ta_pred, tc_pred);
        final_pred.fanout(hard<2> {});
        reg_final_pred = final_pred;

        return final_pred;
    }

    val<1> reuse_predict2([[maybe_unused]] val<64> inst_pc) override
    {
        return reg_final_pred;
    }

    void update_condbr([[maybe_unused]] val<64> branch_pc, val<1> taken, [[maybe_unused]] val<64> next_pc) override
    {
        // 1. Declare fanouts of registers and inputs
        taken.fanout(hard<6> {});
        
        reg_tc_id.fanout(hard<4> {});
        val<1> tc_is_0 = (reg_tc_id == 0);
        val<1> tc_is_1 = (reg_tc_id == 1);
        val<1> tc_is_2 = (reg_tc_id == 2);
        val<1> tc_is_3 = (reg_tc_id == 3);

        tc_is_0.fanout(hard<3> {});
        tc_is_1.fanout(hard<2> {});
        tc_is_3.fanout(hard<2> {});

        val<1> update_t0 = tc_is_0;
        val<1> update_t1 = tc_is_1;
        val<1> update_t2 = tc_is_2;
        val<1> update_t3 = tc_is_3;

        update_t1.fanout(hard<2> {});
        update_t2.fanout(hard<2> {});
        update_t3.fanout(hard<2> {});

        val<1> tc_lt_1 = tc_is_0;
        val<1> tc_lt_2 = tc_is_0 | tc_is_1;
        val<1> tc_lt_3 = ~tc_is_3;

        tc_lt_1.fanout(hard<2> {});

        reg_tc_pred.fanout(hard<2> {});
        alt_pred.fanout(hard<2> {});
        reg_use_alt.fanout(hard<2> {});
        reg_final_pred.fanout(hard<2> {});

        gindex1.fanout(hard<4> {});
        gindex2.fanout(hard<4> {});
        gindex3.fanout(hard<4> {});

        reg_b_ctr.fanout(hard<2> {});
        reg_tc_ctr.fanout(hard<2> {});

        read_u1.fanout(hard<2> {});
        read_u2.fanout(hard<3> {});
        read_u3.fanout(hard<4> {});

        // 2. Compute update conditions
        val<2> new_b_ctr = update_ctr(reg_b_ctr, taken);
        new_b_ctr.fanout(hard<2> {});
        val<1> performing_b_update = update_t0 & (new_b_ctr != reg_b_ctr);
        performing_b_update.fanout(hard<2> {});

        val<3> new_tc_ctr = update_ctr(reg_tc_ctr, taken);
        new_tc_ctr.fanout(hard<3> {});
        val<1> performing_tc_update = (new_tc_ctr != reg_tc_ctr);
        performing_tc_update.fanout(hard<3> {});

        val<1> performing_t1_update = update_t1 & performing_tc_update;
        val<1> performing_t2_update = update_t2 & performing_tc_update;
        val<1> performing_t3_update = update_t3 & performing_tc_update;

        val<1> u_cond = (reg_tc_pred != alt_pred);
        u_cond.fanout(hard<3> {});
        val<1> new_u = select(reg_tc_pred == taken, val<1>{1}, val<1>{0});
        new_u.fanout(hard<3> {});

        val<1> update_u1 = update_t1 & u_cond;
        val<1> update_u2 = update_t2 & u_cond;
        val<1> update_u3 = update_t3 & u_cond;

        // 3. Compute allocation conditions
        val<1> mispredict = (reg_final_pred != taken);
        mispredict.fanout(hard<4> {});

        val<1> eligible1 = mispredict & tc_lt_1 & (read_u1 == 0);
        val<1> eligible2 = mispredict & tc_lt_2 & (read_u2 == 0);
        val<1> eligible3 = mispredict & tc_lt_3 & (read_u3 == 0);

        eligible1.fanout(hard<3> {});
        eligible2.fanout(hard<2> {});

        val<1> alloc1 = eligible1;
        val<1> alloc2 = ~eligible1 & eligible2;
        val<1> alloc3 = ~eligible1 & ~eligible2 & eligible3;

        alloc1.fanout(hard<4> {});
        alloc2.fanout(hard<4> {});
        alloc3.fanout(hard<4> {});

        val<3> init_ctr = select(taken, val<3>{4}, val<3>{3}); // weak Taken (4) or weak NT (3)
        init_ctr.fanout(hard<3> {});

        // 4. Compute decay conditions
        val<1> all_u_1_2_3_are_1 = (read_u1 == 1) & (read_u2 == 1) & (read_u3 == 1);
        val<1> all_u_2_3_are_1 = (read_u2 == 1) & (read_u3 == 1);

        val<1> decay1 = mispredict & tc_lt_1 & all_u_1_2_3_are_1;
        val<1> decay2 = select(tc_is_0, decay1, mispredict & tc_is_1 & all_u_2_3_are_1);
        val<1> decay3 = select(tc_is_0, decay1, select(tc_is_1, decay2, mispredict & tc_is_2 & (read_u3 == 1)));

        decay1.fanout(hard<3> {});
        decay2.fanout(hard<2> {});

        // 5. Combine writes to each table to satisfy "single RAM write per cycle" constraint
        // Tagged Predictors (gpredX) writes
        val<1> write_pred1 = performing_t1_update | alloc1;
        val<1> write_pred2 = performing_t2_update | alloc2;
        val<1> write_pred3 = performing_t3_update | alloc3;

        write_pred1.fanout(hard<2> {});
        write_pred2.fanout(hard<2> {});
        write_pred3.fanout(hard<2> {});

        val<3> new_pred_val1 = select(alloc1, init_ctr, new_tc_ctr);
        val<3> new_pred_val2 = select(alloc2, init_ctr, new_tc_ctr);
        val<3> new_pred_val3 = select(alloc3, init_ctr, new_tc_ctr);

        // Useful bits (ubitX) writes
        val<1> alloc1_or_decay1 = alloc1 | decay1;
        val<1> alloc2_or_decay2 = alloc2 | decay2;
        val<1> alloc3_or_decay3 = alloc3 | decay3;

        alloc1_or_decay1.fanout(hard<2> {});
        alloc2_or_decay2.fanout(hard<2> {});
        alloc3_or_decay3.fanout(hard<2> {});

        val<1> write_u1 = update_u1 | alloc1_or_decay1;
        val<1> write_u2 = update_u2 | alloc2_or_decay2;
        val<1> write_u3 = update_u3 | alloc3_or_decay3;

        write_u1.fanout(hard<2> {});
        write_u2.fanout(hard<2> {});
        write_u3.fanout(hard<2> {});

        val<1> new_u_val1 = select(alloc1_or_decay1, val<1>{0}, new_u);
        val<1> new_u_val2 = select(alloc2_or_decay2, val<1>{0}, new_u);
        val<1> new_u_val3 = select(alloc3_or_decay3, val<1>{0}, new_u);

        // Advancing cycle if updates are performed
        val<1> updates_made = performing_b_update | write_pred1 | write_pred2 | write_pred3 |
                              write_u1 | write_u2 | write_u3 |
                              alloc1 | alloc2 | alloc3;
        need_extra_cycle(updates_made);

        // 6. Write operations (one execute_if block per RAM instance)
        // T0 Base Predictor
        execute_if(performing_b_update, [&]() {
            bim.write(bindex, new_b_ctr);
        });

        // Tagged Predictors (gpredX)
        execute_if(write_pred1, [&]() { gpred1.write(gindex1, new_pred_val1); });
        execute_if(write_pred2, [&]() { gpred2.write(gindex2, new_pred_val2); });
        execute_if(write_pred3, [&]() { gpred3.write(gindex3, new_pred_val3); });

        // Useful bits (ubitX)
        execute_if(write_u1, [&]() { ubit1.write(gindex1, new_u_val1); });
        execute_if(write_u2, [&]() { ubit2.write(gindex2, new_u_val2); });
        execute_if(write_u3, [&]() { ubit3.write(gindex3, new_u_val3); });

        // Tag tables (gtagX)
        execute_if(alloc1, [&]() { gtag1.write(gindex1, gtag_calc1); });
        execute_if(alloc2, [&]() { gtag2.write(gindex2, gtag_calc2); });
        execute_if(alloc3, [&]() { gtag3.write(gindex3, gtag_calc3); });

        // 7. Update BHR and Folded Histories
        val<64> gh_input = val<64> { taken };
        gh.update(gh_input);

        t1_idx_fold.update(gh, hard<8UL> {}, gh_input);
        t1_tag_fold.update(gh, hard<8UL> {}, gh_input);
        t2_idx_fold.update(gh, hard<24UL> {}, gh_input);
        t2_tag_fold.update(gh, hard<24UL> {}, gh_input);
        t3_idx_fold.update(gh, hard<64UL> {}, gh_input);
        t3_tag_fold.update(gh, hard<64UL> {}, gh_input);
    }

    void update_cycle([[maybe_unused]] instruction_info& block_end_info) override
    {
    }
};

#include "../../cbp.hpp"
#include "../../harcom.hpp"
#include <algorithm>

using namespace hcm;

/*
 * Block-based TAGE predictor with Bias Table prefilter for T0 (base table).
 * Idea taken from Bi-Mode++ (bimodepp.hpp).
 */

template <
    u64 PC_B = 10,             // Number of index bits for the TAGE tables
    u64 TAG_B = 8,             // Number of bits for the tags
    u64 HIST_MAX = 64,         // Max size of the Global History Register
    u64 L1 = 4,                // History length for Table 1 (Short)
    u64 L2 = 16,               // History length for Table 2 (Medium)
    u64 L3 = 64,               // History length for Table 3 (Long)
    u64 CTR_B = 3,             // 3-bit counters
    u64 LINE_B = 4,            // 2^LINE_B instructions predicted per cycle
    u64 BIAS_B = 6,            // Number of index bits for the bias table
    bool USE_BIAS_HIST = true, // Use history XOR for bias table index
    u64 T0_BHR_B = 0           // Number of BHR bits to XOR with PC for T0 index (0 to disable)
    >
struct tage_biasL : predictor
{
    static constexpr u64 LI = 1 << LINE_B;
    static constexpr u64 PHT_ROWS = 1 << PC_B;
    static constexpr u64 BIAS_ROWS = 1 << BIAS_B;
    static constexpr u64 ENTRY_BITS = (CTR_B * LI) + TAG_B;

    // TABLES (Line-based structures)
    ram<arr<val<CTR_B>, LI>, PHT_ROWS> t0; // Wide base table
    ram<val<ENTRY_BITS>, PHT_ROWS> t1;     // Sectored Tagged tables
    ram<val<ENTRY_BITS>, PHT_ROWS> t2;
    ram<val<ENTRY_BITS>, PHT_ROWS> t3;
    ram<arr<val<2>, LI>, BIAS_ROWS> bias_table; // Bias table

    // Global History
    reg<HIST_MAX> ghr;

    // Registers for Update/Reuse Tracking
    reg<2> provider_id;
    arr<reg<CTR_B>, LI> final_counters;
    arr<reg<CTR_B>, LI> reg_ctr0;

    reg<PC_B> reg_idx0, reg_idx1, reg_idx2, reg_idx3;
    reg<TAG_B> reg_tag1, reg_tag2, reg_tag3;

    reg<BIAS_B> reg_idx_bias;
    arr<reg<2>, LI> reg_bias0;

    // Record values from per-branch updates to be used in per-cacheline update logic
    u64 num_branches = 0;
    arr<reg<LINE_B>, LI> branch_offset;
    arr<reg<1>, LI> branch_taken;

    val<CTR_B> update_counter(val<CTR_B> ctr, val<1> incr)
    {
        ctr.fanout(hard<2> {});
        val<CTR_B> increased = select(ctr == hard<ctr.maxval> {}, ctr, val<CTR_B> { ctr + 1 });
        val<CTR_B> decreased = select(ctr == hard<ctr.minval> {}, ctr, val<CTR_B> { ctr - 1 });
        return select(incr.fo1(), increased.fo1(), decreased.fo1());
    }

    val<1> predict1(val<64> inst_pc) override
    {
        // Reset the branch counter for this new prediction block
        num_branches = 0;

        inst_pc.fanout(hard<3> {});

        // Compute Block PC index (Strip alignment and offset bits)
        val<PC_B> block_pc = val<PC_B> { inst_pc >> (2 + LINE_B) };

        // Index Generation for T0 (supporting optional BHR XOR)
        val<PC_B> idx0 = [&]() {
            val<PC_B> base_idx = block_pc.fo1();
            if constexpr (T0_BHR_B > 0)
            {
                return base_idx ^ (val<PC_B> { ghr } & val<PC_B> { (1ULL << T0_BHR_B) - 1 });
            }
            else
            {
                return base_idx;
            }
        }();
        idx0.fanout(hard<2> {});
        reg_idx0 = idx0;

        // Perform SRAM Line Read for T0
        arr<val<CTR_B>, LI> ctr0 = t0.read(idx0.fo1());
        ctr0.fanout(hard<2> {});
        reg_ctr0 = ctr0;

        // Index Generation for Bias Table
        val<BIAS_B> idx_bias = [&]() {
            if constexpr (USE_BIAS_HIST)
            {
                return val<BIAS_B> { inst_pc >> (2 + LINE_B) } ^ val<BIAS_B> { ghr };
            }
            else
            {
                return val<BIAS_B> { inst_pc >> (2 + LINE_B) };
            }
        }();
        idx_bias.fanout(hard<2> {});
        reg_idx_bias = idx_bias;

        // Perform SRAM Line Read for Bias Table
        arr<val<2>, LI> bias0 = bias_table.read(idx_bias.fo1());
        bias0.fanout(hard<2> {});
        reg_bias0 = bias0;

        val<LINE_B> offset = val<LINE_B> { inst_pc.fo1() >> 2 };
        offset.fanout(hard<2> {});

        val<1> t0_pred = ctr0.fo1().select(offset) >> (CTR_B - 1);

        val<2> b_val = bias0.fo1().select(offset.fo1());
        b_val.fanout(hard<2> {});
        val<1> untaken_biased = ~(b_val >> 1);
        val<1> taken_biased = ~(b_val.fo1() & 1);
        untaken_biased.fanout(hard<2> {});

        return select(untaken_biased.fo1(), val<1> { 0 }, select(taken_biased.fo1(), val<1> { 1 }, t0_pred.fo1()));
    }

    val<1> predict2(val<64> inst_pc) override
    {
        inst_pc.fanout(hard<5> {});
        ghr.fanout(hard<6> {});

        // Compute Block PC index (Strip alignment and offset bits)
        val<PC_B> block_pc = val<PC_B> { inst_pc >> (2 + LINE_B) };
        block_pc.fanout(hard<3> {});

        // Index and Tag Generations
        val<PC_B> idx1 = block_pc ^ val<PC_B> { ghr };
        val<TAG_B> tag1 = val<TAG_B> { inst_pc >> (2 + LINE_B + PC_B) } ^ val<TAG_B> { ghr >> 1 };
        idx1.fanout(hard<2> {});
        tag1.fanout(hard<2> {});
        reg_idx1 = idx1;
        reg_tag1 = tag1;

        val<PC_B> idx2 = block_pc ^ val<PC_B> { ghr >> 2 };
        val<TAG_B> tag2 = val<TAG_B> { inst_pc >> (2 + LINE_B + PC_B) } ^ val<TAG_B> { ghr >> 3 };
        idx2.fanout(hard<2> {});
        tag2.fanout(hard<2> {});
        reg_idx2 = idx2;
        reg_tag2 = tag2;

        val<PC_B> idx3 = block_pc ^ val<PC_B> { ghr >> 4 };
        val<TAG_B> tag3 = val<TAG_B> { inst_pc >> (2 + LINE_B + PC_B) } ^ val<TAG_B> { ghr >> 5 };
        idx3.fanout(hard<2> {});
        tag3.fanout(hard<2> {});
        reg_idx3 = idx3;
        reg_tag3 = tag3;

        // Perform Parallel SRAM Line Reads for tagged components
        val<ENTRY_BITS> raw1 = t1.read(idx1.fo1());
        val<ENTRY_BITS> raw2 = t2.read(idx2.fo1());
        val<ENTRY_BITS> raw3 = t3.read(idx3.fo1());

        // Unpack Sectored [ Counters Line | Tag ] Fields
        auto [flat_ctr1, stored_tag1] = split<CTR_B * LI, TAG_B>(raw1.fo1());
        auto [flat_ctr2, stored_tag2] = split<CTR_B * LI, TAG_B>(raw2.fo1());
        auto [flat_ctr3, stored_tag3] = split<CTR_B * LI, TAG_B>(raw3.fo1());

        arr<val<CTR_B>, LI> ctr1 = [&](u64 i) { return val<CTR_B> { flat_ctr1 >> (i * CTR_B) }; };
        arr<val<CTR_B>, LI> ctr2 = [&](u64 i) { return val<CTR_B> { flat_ctr2 >> (i * CTR_B) }; };
        arr<val<CTR_B>, LI> ctr3 = [&](u64 i) { return val<CTR_B> { flat_ctr3 >> (i * CTR_B) }; };

        // Evaluate Tag Hits across entire line
        val<1> hit1 = (L1 > 0) ? (stored_tag1 == tag1.fo1()) : val<1> { 0 };
        val<1> hit2 = (L2 > 0) ? (stored_tag2 == tag2.fo1()) : val<1> { 0 };
        val<1> hit3 = (L3 > 0) ? (stored_tag3 == tag3.fo1()) : val<1> { 0 };

        hit1.fanout(hard<2> {});
        hit2.fanout(hard<3> {});
        hit3.fanout(hard<4> {});

        // Elementwise Multi-table Vector Selection using reg_ctr0 fallback
        arr<val<CTR_B>, LI> selected_counters = [&](u64 i) {
            return select(hit3, ctr3[i],
                          select(hit2, ctr2[i],
                                 select(hit1, ctr1[i], reg_ctr0[i])));
        };

        final_counters = selected_counters;

        provider_id = select(hit3, val<2> { 3 },
                             select(hit2, val<2> { 2 },
                                    select(hit1, val<2> { 1 }, val<2> { 0 })));

        val<1> any_tag_hit = hit3 | hit2 | hit1;

        val<LINE_B> offset = val<LINE_B> { inst_pc >> 2 };
        offset.fanout(hard<4> {});
        reuse_prediction(offset != hard<LI - 1> {});

        // T0 prefiltered prediction
        val<1> t0_pred = reg_ctr0.select(offset) >> (CTR_B - 1);
        val<2> b_val = reg_bias0.select(offset);
        b_val.fanout(hard<2> {});
        val<1> untaken_biased = ~(b_val >> 1);
        val<1> taken_biased = ~(b_val & 1);
        val<1> t0_prefiltered_pred = select(untaken_biased.fo1(), val<1> { 0 }, select(taken_biased, val<1> { 1 }, t0_pred));

        val<1> final_ctr_pred = val<1> { final_counters.select(offset) >> (CTR_B - 1) };
        return select(any_tag_hit.fo1(), final_ctr_pred.fo1(), t0_prefiltered_pred.fo1());
    }

    val<1> reuse_predict1(val<64> inst_pc) override
    {
        val<LINE_B> offset = val<LINE_B> { inst_pc.fo1() >> 2 };
        offset.fanout(hard<2> {});
        val<1> t0_pred = reg_ctr0.select(offset) >> (CTR_B - 1);

        val<2> b_val = reg_bias0.select(offset);
        b_val.fanout(hard<2> {});
        val<1> untaken_biased = ~(b_val >> 1);
        val<1> taken_biased = ~(b_val & 1);

        return select(untaken_biased.fo1(), val<1> { 0 }, select(taken_biased.fo1(), val<1> { 1 }, t0_pred.fo1()));
    }

    val<1> reuse_predict2(val<64> inst_pc) override
    {
        val<LINE_B> offset = val<LINE_B> { inst_pc.fo1() >> 2 };
        offset.fanout(hard<4> {});
        reuse_prediction(offset != hard<LI - 1> {});

        val<1> any_tag_hit = (provider_id != hard<0> {});

        val<1> t0_pred = reg_ctr0.select(offset) >> (CTR_B - 1);
        val<2> b_val = reg_bias0.select(offset);
        b_val.fanout(hard<2> {});
        val<1> untaken_biased = ~(b_val >> 1);
        val<1> taken_biased = ~(b_val & 1);
        val<1> t0_prefiltered_pred = select(untaken_biased.fo1(), val<1> { 0 }, select(taken_biased.fo1(), val<1> { 1 }, t0_pred.fo1()));

        val<1> final_ctr_pred = val<1> { final_counters.select(offset) >> (CTR_B - 1) };
        return select(any_tag_hit.fo1(), final_ctr_pred.fo1(), t0_prefiltered_pred.fo1());
    }

    void update_condbr(val<64> branch_pc, val<1> taken, [[maybe_unused]] val<64> next_pc) override
    {
        // Record branch execution states
        branch_offset[num_branches] = branch_pc.fo1() >> 2;
        branch_taken[num_branches] = taken.fo1();
        num_branches++;
    }

    void update_cycle([[maybe_unused]] instruction_info& block_end_info) override
    {
        // update the BHR
        val<LI> new_history = branch_taken.concat().reverse() >> (LI - num_branches);
        val<HIST_MAX> new_ghr = (ghr << num_branches) + new_history.fo1();
        new_ghr.fanout(hard<2> {});

        val<1> performing_update_ghr = val<1> { new_ghr != ghr };
        performing_update_ghr.fanout(hard<2> {});

        // we obtain cacheline row masks
        arr<val<LI>, LI> branch_onehot = [&](u64 i) {
            val<LI> valid_mask = val<1> { i < num_branches }.replicate(hard<LI> {}).concat();
            return valid_mask.fo1() & branch_offset[i].decode().concat();
        };
        val<LI> branch_mask = branch_onehot.fold_or();

        arr<val<LI>, LI> taken_onehot = [&](u64 i) {
            return branch_onehot[i] & branch_taken[i].replicate(hard<LI> {}).concat();
        };
        val<LI> taken_mask = taken_onehot.fold_or();

        branch_mask.fanout(hard<LI> {});
        taken_mask.fanout(hard<LI> {});

        val<1> is_p0 = (provider_id == hard<0> {});
        val<1> is_p1 = (provider_id == hard<1> {});
        val<1> is_p2 = (provider_id == hard<2> {});
        val<1> is_p3 = (provider_id == hard<3> {});

        is_p0.fanout(hard<3> {});
        is_p1.fanout(hard<3> {});
        is_p2.fanout(hard<3> {});
        is_p3.fanout(hard<2> {});

        // Compute row-wide validation masks for whether components need a row rewrite
        arr<val<1>, LI> array_write_t0 = [&](u64 i) {
            val<1> has_branch = val<1> { branch_mask >> i };
            val<1> taken_bit = val<1> { taken_mask >> i };
            val<CTR_B> orig_ctr = final_counters[i];
            val<CTR_B> updated_ctr = update_counter(orig_ctr, taken_bit);
            val<1> is_unbiased = (reg_bias0[i] == val<2> { 3 });
            return has_branch & (is_p0 & is_unbiased & (updated_ctr != orig_ctr));
        };

        arr<val<1>, LI> array_write_t1 = [&](u64 i) {
            val<1> has_branch = val<1> { branch_mask >> i };
            val<1> taken_bit = val<1> { taken_mask >> i };
            val<CTR_B> orig_ctr = final_counters[i];
            val<CTR_B> updated_ctr = update_counter(orig_ctr, taken_bit);
            val<1> mispred = (orig_ctr >> (CTR_B - 1)) ^ taken_bit;
            return has_branch & ((is_p1 & (updated_ctr != orig_ctr)) | (mispred & is_p0 & (L1 > 0)));
        };

        arr<val<1>, LI> array_write_t2 = [&](u64 i) {
            val<1> has_branch = val<1> { branch_mask >> i };
            val<1> taken_bit = val<1> { taken_mask >> i };
            val<CTR_B> orig_ctr = final_counters[i];
            val<CTR_B> updated_ctr = update_counter(orig_ctr, taken_bit);
            val<1> mispred = (orig_ctr >> (CTR_B - 1)) ^ taken_bit;
            return has_branch & ((is_p2 & (updated_ctr != orig_ctr)) | (mispred & is_p1 & (L2 > 0)));
        };

        arr<val<1>, LI> array_write_t3 = [&](u64 i) {
            val<1> has_branch = val<1> { branch_mask >> i };
            val<1> taken_bit = val<1> { taken_mask >> i };
            val<CTR_B> orig_ctr = final_counters[i];
            val<CTR_B> updated_ctr = update_counter(orig_ctr, taken_bit);
            val<1> mispred = (orig_ctr >> (CTR_B - 1)) ^ taken_bit;
            return has_branch & ((is_p3 & (updated_ctr != orig_ctr)) | (mispred & is_p2 & (L3 > 0)));
        };

        arr<val<1>, LI> array_write_bias = [&](u64 i) {
            val<1> has_branch = val<1> { branch_mask >> i };
            val<2> orig_bias = reg_bias0[i];
            orig_bias.fanout(hard<2> {});
            val<1> taken_bit = val<1> { taken_mask >> i };
            val<2> bit_to_set = select(taken_bit, val<2> { 2 }, val<2> { 1 });
            val<2> new_bias = orig_bias | bit_to_set;
            return has_branch & (new_bias != orig_bias.fo1());
        };

        // Determine master single-cycle parallel RAM access indicators
        val<1> write_t0 = (array_write_t0.concat() != hard<0> {});
        val<1> write_t1 = (array_write_t1.concat() != hard<0> {});
        val<1> write_t2 = (array_write_t2.concat() != hard<0> {});
        val<1> write_t3 = (array_write_t3.concat() != hard<0> {});
        val<1> write_bias = (array_write_bias.concat() != hard<0> {});

        write_t0.fanout(hard<2> {});
        write_t1.fanout(hard<2> {});
        write_t2.fanout(hard<2> {});
        write_t3.fanout(hard<2> {});
        write_bias.fanout(hard<2> {});

        val<1> performing_update = write_t0 | write_t1 | write_t2 | write_t3 | write_bias | performing_update_ghr;
        need_extra_cycle(performing_update);

        // Generate the new full arrays for each table line
        arr<val<CTR_B>, LI> new_t0_counters = [&](u64 i) {
            val<1> has_branch = val<1> { branch_mask >> i };
            val<1> taken_bit = val<1> { taken_mask >> i };
            val<CTR_B> orig_ctr = final_counters[i];
            val<CTR_B> updated_ctr = update_counter(orig_ctr, taken_bit);
            val<1> is_unbiased = (reg_bias0[i] == val<2> { 3 });
            return select(has_branch & is_p0 & is_unbiased, updated_ctr, orig_ctr);
        };

        arr<val<CTR_B>, LI> new_t1_counters = [&](u64 i) {
            val<1> has_branch = val<1> { branch_mask >> i };
            val<1> taken_bit = val<1> { taken_mask >> i };
            val<CTR_B> orig_ctr = final_counters[i];
            val<CTR_B> updated_ctr = update_counter(orig_ctr, taken_bit);
            val<CTR_B> alloc_val = select(taken_bit, val<CTR_B> { 4 }, val<CTR_B> { 3 });
            return select(is_p1,
                          select(has_branch, updated_ctr, orig_ctr),
                          select(has_branch, alloc_val, val<CTR_B> { 3 }));
        };

        arr<val<CTR_B>, LI> new_t2_counters = [&](u64 i) {
            val<1> has_branch = val<1> { branch_mask >> i };
            val<1> taken_bit = val<1> { taken_mask >> i };
            val<CTR_B> orig_ctr = final_counters[i];
            val<CTR_B> updated_ctr = update_counter(orig_ctr, taken_bit);
            val<CTR_B> alloc_val = select(taken_bit, val<CTR_B> { 4 }, val<CTR_B> { 3 });
            return select(is_p2,
                          select(has_branch, updated_ctr, orig_ctr),
                          select(has_branch, alloc_val, val<CTR_B> { 3 }));
        };

        arr<val<CTR_B>, LI> new_t3_counters = [&](u64 i) {
            val<1> has_branch = val<1> { branch_mask >> i };
            val<1> taken_bit = val<1> { taken_mask >> i };
            val<CTR_B> orig_ctr = final_counters[i];
            val<CTR_B> updated_ctr = update_counter(orig_ctr, taken_bit);
            val<CTR_B> alloc_val = select(taken_bit, val<CTR_B> { 4 }, val<CTR_B> { 3 });
            return select(is_p3,
                          select(has_branch, updated_ctr, orig_ctr),
                          select(has_branch, alloc_val, val<CTR_B> { 3 }));
        };

        arr<val<2>, LI> new_bias_line = [&](u64 i) {
            val<1> has_branch = val<1> { branch_mask >> i };
            val<1> taken_bit = val<1> { taken_mask >> i };
            val<2> orig_bias = reg_bias0[i];
            orig_bias.fanout(hard<2> {});
            val<2> bit_to_set = select(taken_bit, val<2> { 2 }, val<2> { 1 });
            val<2> new_bias = orig_bias | bit_to_set;
            return select(has_branch, new_bias, orig_bias);
        };

        // Write atomic sector blocks back to RAM rows in exactly one shot
        execute_if(write_t0.fo1(), [&]() {
            t0.write(reg_idx0, new_t0_counters);
        });

        execute_if(write_t1.fo1(), [&]() {
            val<ENTRY_BITS> packed1 = concat(new_t1_counters.concat(), reg_tag1);
            t1.write(reg_idx1, packed1.fo1());
        });

        execute_if(write_t2.fo1(), [&]() {
            val<ENTRY_BITS> packed2 = concat(new_t2_counters.concat(), reg_tag2);
            t2.write(reg_idx2, packed2.fo1());
        });

        execute_if(write_t3.fo1(), [&]() {
            val<ENTRY_BITS> packed3 = concat(new_t3_counters.concat(), reg_tag3);
            t3.write(reg_idx3, packed3.fo1());
        });

        execute_if(write_bias.fo1(), [&]() {
            bias_table.write(reg_idx_bias, new_bias_line);
        });

        execute_if(performing_update_ghr, [&]() {
            ghr = new_ghr;
        });
    }
};

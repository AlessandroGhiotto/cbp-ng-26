#include "../../cbp.hpp"
#include "../../harcom.hpp"
#include <algorithm>

using namespace hcm;

/*
 * Block-based TAGE predictor with Bi-Mode base predictor (replacing T0)
 * and optional Bias Table prefilter.
 */

template <
    u64 PC_B = 10,            // Number of index bits for TAGE tagged tables
    u64 TAG_B = 8,            // Number of bits for the tags
    u64 HIST_MAX = 64,        // Max size of the Global History Register
    u64 L1 = 4,               // History length for Table 1 (Short)
    u64 L2 = 16,              // History length for Table 2 (Medium)
    u64 L3 = 64,              // History length for Table 3 (Long)
    u64 CTR_B = 3,            // Counters width
    u64 LINE_B = 4,           // 2^LINE_B instructions predicted per cycle
    u64 BIAS_B = 6,           // Number of index bits for the bias table
    bool USE_BIAS_HIST = true, // Use history XOR for bias table index
    u64 CHOICE_B = 10,         // Choice PHT index size for Bi-Mode base
    u64 PHT_B = 10,            // Taken/Not-Taken PHT index size for Bi-Mode base
    u64 T0_BHR_B = 8,          // BHR bits to XOR with PC for Bi-Mode base index
    bool USE_BIAS = false      // Enable bias table prefilter
    >
struct tage_bimodeL : predictor
{
    static constexpr u64 LI = 1 << LINE_B;
    static constexpr u64 PHT_ROWS = 1 << PC_B;
    static constexpr u64 CHOICE_ROWS = 1 << CHOICE_B;
    static constexpr u64 PHT_BASE_ROWS = 1 << PHT_B;
    static constexpr u64 BIAS_ROWS = 1 << BIAS_B;
    static constexpr u64 ENTRY_BITS = (CTR_B * LI) + TAG_B;

    // TABLES
    ram<arr<val<CTR_B>, LI>, CHOICE_ROWS> choice_table;
    ram<arr<val<CTR_B>, LI>, PHT_BASE_ROWS> taken_pht;
    ram<arr<val<CTR_B>, LI>, PHT_BASE_ROWS> not_taken_pht;
    ram<val<ENTRY_BITS>, PHT_ROWS> t1;
    ram<val<ENTRY_BITS>, PHT_ROWS> t2;
    ram<val<ENTRY_BITS>, PHT_ROWS> t3;
    ram<arr<val<2>, LI>, BIAS_ROWS> bias_table;

    // Global History
    reg<HIST_MAX> ghr;

    // Registers for Update/Reuse Tracking
    reg<2> provider_id;
    arr<reg<CTR_B>, LI> final_counters;

    reg<PC_B> reg_idx1, reg_idx2, reg_idx3;
    reg<TAG_B> reg_tag1, reg_tag2, reg_tag3;

    // Bi-Mode base tracking registers
    reg<CHOICE_B> reg_choice_idx;
    arr<reg<CTR_B>, LI> reg_choice_line;
    reg<LI> reg_choice_val_line;

    reg<PHT_B> reg_pht_idx;
    arr<reg<CTR_B>, LI> reg_base_ctr_line;
    arr<reg<CTR_B>, LI> reg_taken_line;
    arr<reg<CTR_B>, LI> reg_not_taken_line;

    // Bias table registers
    reg<BIAS_B> reg_idx_bias;
    arr<reg<2>, LI> reg_bias0;

    // Record values from per-branch updates
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
        num_branches = 0;

        static constexpr u64 INST_PC_USES = USE_BIAS ? 3 : 2;
        inst_pc.fanout(hard<INST_PC_USES> {});

        // Index Choice Table
        val<CHOICE_B> choice_row_idx = [&]() {
            val<CHOICE_B> base_idx = val<CHOICE_B> { inst_pc >> (2 + LINE_B) };
            if constexpr (T0_BHR_B > 0) {
                return base_idx ^ (val<CHOICE_B> { ghr } & val<CHOICE_B> { (1ULL << T0_BHR_B) - 1 });
            } else {
                return base_idx;
            }
        }();
        choice_row_idx.fanout(hard<2> {});
        reg_choice_idx = choice_row_idx;

        arr<val<CTR_B>, LI> choice_line = choice_table.read(choice_row_idx);
        choice_line.fanout(hard<2> {});
        reg_choice_line = choice_line;

        arr<val<1>, LI> choice_preds = [&](u64 i) {
            return choice_line[i] >> (CTR_B - 1);
        };
        choice_preds.fanout(hard<2> {});
        reg_choice_val_line = choice_preds.concat();

        val<LINE_B> offset = [&]() {
            return val<LINE_B> { inst_pc >> 2 };
        }();
        offset.fanout(hard<2> {});

        val<1> choice_pred = choice_preds.select(offset);

        if constexpr (USE_BIAS) {
            val<BIAS_B> idx_bias = [&]() {
                if constexpr (USE_BIAS_HIST) {
                    return val<BIAS_B> { inst_pc >> (2 + LINE_B) } ^ val<BIAS_B> { ghr };
                } else {
                    return val<BIAS_B> { inst_pc >> (2 + LINE_B) };
                }
            }();

            arr<val<2>, LI> bias0 = bias_table.read(idx_bias.fo1());
            bias0.fanout(hard<2> {});
            reg_bias0 = bias0;

            val<2> b_val = bias0.select(offset);
            b_val.fanout(hard<2> {});
            val<1> untaken_biased = ~(b_val >> 1);
            val<1> taken_biased = ~(b_val & 1);
            return select(untaken_biased.fo1(), val<1> { 0 }, select(taken_biased.fo1(), val<1> { 1 }, choice_pred.fo1()));
        } else {
            return choice_pred;
        }
    }

    val<1> predict2(val<64> inst_pc) override
    {
        inst_pc.fanout(hard<6> {});
        ghr.fanout(hard<7> {});

        // Compute Block PC index for TAGE tagged tables
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
        val<ENTRY_BITS> raw1 = t1.read(idx1);
        val<ENTRY_BITS> raw2 = t2.read(idx2);
        val<ENTRY_BITS> raw3 = t3.read(idx3);

        // Unpack Sectored [ Counters Line | Tag ] Fields
        auto [flat_ctr1, stored_tag1] = split<CTR_B * LI, TAG_B>(raw1.fo1());
        auto [flat_ctr2, stored_tag2] = split<CTR_B * LI, TAG_B>(raw2.fo1());
        auto [flat_ctr3, stored_tag3] = split<CTR_B * LI, TAG_B>(raw3.fo1());

        arr<val<CTR_B>, LI> ctr1 = [&](u64 i) { return val<CTR_B> { flat_ctr1 >> (i * CTR_B) }; };
        arr<val<CTR_B>, LI> ctr2 = [&](u64 i) { return val<CTR_B> { flat_ctr2 >> (i * CTR_B) }; };
        arr<val<CTR_B>, LI> ctr3 = [&](u64 i) { return val<CTR_B> { flat_ctr3 >> (i * CTR_B) }; };

        // Evaluate Tag Hits across entire line
        val<1> hit1 = (L1 > 0) ? (stored_tag1 == tag1) : val<1> { 0 };
        val<1> hit2 = (L2 > 0) ? (stored_tag2 == tag2) : val<1> { 0 };
        val<1> hit3 = (L3 > 0) ? (stored_tag3 == tag3) : val<1> { 0 };

        hit1.fanout(hard<3> {});
        hit2.fanout(hard<4> {});
        hit3.fanout(hard<5> {});

        // Compute base predictor PHT index
        val<PHT_B> pht_row_idx = val<PHT_B> { inst_pc >> (2 + LINE_B) } ^ val<PHT_B> { ghr };
        pht_row_idx.fanout(hard<2> {});
        reg_pht_idx = pht_row_idx;

        // Read Taken and Not-Taken base PHTs
        arr<val<CTR_B>, LI> t_line = taken_pht.read(pht_row_idx);
        arr<val<CTR_B>, LI> nt_line = not_taken_pht.read(pht_row_idx);
        t_line.fanout(hard<2> {});
        nt_line.fanout(hard<2> {});
        reg_taken_line = t_line;
        reg_not_taken_line = nt_line;

        arr<val<1>, LI> choice_preds = reg_choice_val_line.make_array(val<1> {});

        arr<val<CTR_B>, LI> base_ctr_line = [&](u64 i) {
            return select(choice_preds[i], t_line[i], nt_line[i]);
        };
        base_ctr_line.fanout(hard<3> {});
        reg_base_ctr_line = base_ctr_line;

        // Elementwise Multi-table Vector Selection using base_ctr_line fallback
        arr<val<CTR_B>, LI> selected_counters = [&](u64 i) {
            return select(hit3, ctr3[i],
                          select(hit2, ctr2[i],
                                 select(hit1, ctr1[i], base_ctr_line[i])));
        };
        final_counters = selected_counters;

        provider_id = select(hit3, val<2> { 3 },
                             select(hit2, val<2> { 2 },
                                    select(hit1, val<2> { 1 }, val<2> { 0 })));

        val<1> any_tag_hit = hit3 | hit2 | hit1;

        val<LINE_B> offset = val<LINE_B> { inst_pc >> 2 };
        offset.fanout(hard<4> {});
        reuse_prediction(offset != hard<LI - 1> {});

        // Bi-Mode base prefiltered prediction
        val<1> base_raw_pred = base_ctr_line.select(offset) >> (CTR_B - 1);
        val<1> base_pred = [&]() {
            if constexpr (USE_BIAS) {
                val<2> b_val = reg_bias0.select(offset);
                b_val.fanout(hard<2> {});
                val<1> untaken_biased = ~(b_val >> 1);
                val<1> taken_biased = ~(b_val & 1);
                return select(untaken_biased.fo1(), val<1> { 0 }, select(taken_biased.fo1(), val<1> { 1 }, base_raw_pred.fo1()));
            } else {
                return base_raw_pred;
            }
        }();

        val<1> final_ctr_pred = val<1> { final_counters.select(offset) >> (CTR_B - 1) };
        return select(any_tag_hit.fo1(), final_ctr_pred.fo1(), base_pred.fo1());
    }

    val<1> reuse_predict1(val<64> inst_pc) override
    {
        val<LINE_B> offset = val<LINE_B> { inst_pc >> 2 };
        offset.fanout(hard<2> {});

        arr<val<1>, LI> choice_preds = reg_choice_val_line.make_array(val<1> {});
        val<1> choice_pred = choice_preds.fo1().select(offset);

        if constexpr (USE_BIAS) {
            val<2> b_val = reg_bias0.select(offset);
            b_val.fanout(hard<2> {});
            val<1> untaken_biased = ~(b_val >> 1);
            val<1> taken_biased = ~(b_val & 1);
            return select(untaken_biased.fo1(), val<1> { 0 }, select(taken_biased.fo1(), val<1> { 1 }, choice_pred.fo1()));
        } else {
            return choice_pred;
        }
    }

    val<1> reuse_predict2(val<64> inst_pc) override
    {
        val<LINE_B> offset = val<LINE_B> { inst_pc >> 2 };
        offset.fanout(hard<4> {});
        reuse_prediction(offset != hard<LI - 1> {});

        val<1> any_tag_hit = (provider_id != hard<0> {});

        val<1> base_raw_pred = reg_base_ctr_line.select(offset) >> (CTR_B - 1);
        val<1> base_pred = [&]() {
            if constexpr (USE_BIAS) {
                val<2> b_val = reg_bias0.select(offset);
                b_val.fanout(hard<2> {});
                val<1> untaken_biased = ~(b_val >> 1);
                val<1> taken_biased = ~(b_val & 1);
                return select(untaken_biased.fo1(), val<1> { 0 }, select(taken_biased.fo1(), val<1> { 1 }, base_raw_pred.fo1()));
            } else {
                return base_raw_pred;
            }
        }();

        val<1> final_ctr_pred = val<1> { final_counters.select(offset) >> (CTR_B - 1) };
        return select(any_tag_hit.fo1(), final_ctr_pred.fo1(), base_pred.fo1());
    }

    void update_condbr(val<64> branch_pc, val<1> taken, [[maybe_unused]] val<64> next_pc) override
    {
        branch_offset[num_branches] = branch_pc >> 2;
        branch_taken[num_branches] = taken;
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

        // row masks
        arr<val<LI>, LI> branch_onehot = [&](u64 i) {
            val<LI> valid_mask = val<1> { i < num_branches }.replicate(hard<LI> {}).concat();
            return valid_mask.fo1() & branch_offset[i].decode().concat();
        };
        val<LI> branch_mask = branch_onehot.fold_or();

        arr<val<LI>, LI> taken_onehot = [&](u64 i) {
            return branch_onehot[i] & branch_taken[i].replicate(hard<LI> {}).concat();
        };
        val<LI> taken_mask = taken_onehot.fold_or();

        static constexpr u64 MASK_USES = USE_BIAS ? 12 : 10;
        branch_mask.fanout(hard<MASK_USES> {});
        taken_mask.fanout(hard<MASK_USES> {});

        val<1> is_p0 = (provider_id == hard<0> {});
        val<1> is_p1 = (provider_id == hard<1> {});
        val<1> is_p2 = (provider_id == hard<2> {});
        val<1> is_p3 = (provider_id == hard<3> {});

        is_p0.fanout(hard<2> {});
        is_p1.fanout(hard<3> {});
        is_p2.fanout(hard<3> {});
        is_p3.fanout(hard<2> {});

        // Base update condition
        arr<val<1>, LI> base_update_enable = [&](u64 i) {
            if constexpr (USE_BIAS) {
                return is_p0 & (reg_bias0[i] == val<2> { 3 });
            } else {
                return is_p0;
            }
        };

        // Compute row-wide validation masks
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

        arr<val<CTR_B>, LI> new_choice_line = [&](u64 i) {
            val<1> is_exec = val<1> { branch_mask >> i };
            val<1> is_taken = val<1> { taken_mask >> i };
            val<CTR_B> updated_ctr = update_counter(reg_choice_line[i], is_taken.fo1());
            val<1> update_choice = is_exec & base_update_enable[i];
            return select(update_choice, updated_ctr, reg_choice_line[i]);
        };
        new_choice_line.fanout(hard<2> {});

        arr<val<CTR_B>, LI> new_pht_line = [&](u64 i) {
            val<1> is_exec = val<1> { branch_mask >> i };
            val<1> is_taken = val<1> { taken_mask >> i };
            val<CTR_B> updated_ctr = update_counter(reg_base_ctr_line[i], is_taken.fo1());
            val<1> update_pht = is_exec & base_update_enable[i];
            return select(update_pht, updated_ctr, reg_base_ctr_line[i]);
        };
        new_pht_line.fanout(hard<2> {});

        arr<val<1>, LI> choice_val_line = reg_choice_val_line.make_array(val<1> {});

        arr<val<CTR_B>, LI> new_taken_line = [&](u64 i) {
            val<1> is_chosen = choice_val_line[i];
            val<1> is_exec = val<1> { branch_mask >> i };
            val<1> update_taken = is_exec & base_update_enable[i] & is_chosen;
            return select(update_taken, new_pht_line[i], reg_taken_line[i]);
        };
        new_taken_line.fanout(hard<2> {});

        arr<val<CTR_B>, LI> new_not_taken_line = [&](u64 i) {
            val<1> is_chosen = choice_val_line[i];
            val<1> is_exec = val<1> { branch_mask >> i };
            val<1> update_not_taken = is_exec & base_update_enable[i] & ~is_chosen;
            return select(update_not_taken, new_pht_line[i], reg_not_taken_line[i]);
        };
        new_not_taken_line.fanout(hard<2> {});

        val<1> write_choice = (new_choice_line.concat() != reg_choice_line.concat());
        val<1> write_taken = (new_taken_line.concat() != reg_taken_line.concat());
        val<1> write_not_taken = (new_not_taken_line.concat() != reg_not_taken_line.concat());

        write_choice.fanout(hard<2> {});
        write_taken.fanout(hard<2> {});
        write_not_taken.fanout(hard<2> {});

        val<1> write_t1 = (array_write_t1.concat() != hard<0> {});
        val<1> write_t2 = (array_write_t2.concat() != hard<0> {});
        val<1> write_t3 = (array_write_t3.concat() != hard<0> {});

        val<1> write_bias = [&]() {
            if constexpr (USE_BIAS) {
                arr<val<1>, LI> array_write_bias = [&](u64 i) {
                    val<1> has_branch = val<1> { branch_mask >> i };
                    val<2> orig_bias = reg_bias0[i];
                    orig_bias.fanout(hard<2> {});
                    val<1> taken_bit = val<1> { taken_mask >> i };
                    val<2> bit_to_set = select(taken_bit, val<2> { 2 }, val<2> { 1 });
                    val<2> new_bias = orig_bias | bit_to_set;
                    return has_branch & (new_bias != orig_bias.fo1());
                };
                return (array_write_bias.concat() != hard<0> {});
            } else {
                return val<1> { 0 };
            }
        }();
        write_bias.fanout(hard<2> {});

        val<1> performing_update = [&]() {
            val<1> base_upd = write_t1 | write_t2 | write_t3 | write_choice | write_taken | write_not_taken | performing_update_ghr;
            if constexpr (USE_BIAS) {
                return base_upd | write_bias;
            } else {
                return base_upd;
            }
        }();
        need_extra_cycle(performing_update);

        // Generate new full arrays for each TAGE table line
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

        // Write atomic sector blocks back to RAM rows
        execute_if(write_choice, [&]() {
            choice_table.write(reg_choice_idx, new_choice_line);
        });

        execute_if(write_taken, [&]() {
            taken_pht.write(reg_pht_idx, new_taken_line);
        });

        execute_if(write_not_taken, [&]() {
            not_taken_pht.write(reg_pht_idx, new_not_taken_line);
        });

        execute_if(write_t1, [&]() {
            val<ENTRY_BITS> packed1 = concat(new_t1_counters.concat(), reg_tag1);
            t1.write(reg_idx1, packed1.fo1());
        });

        execute_if(write_t2, [&]() {
            val<ENTRY_BITS> packed2 = concat(new_t2_counters.concat(), reg_tag2);
            t2.write(reg_idx2, packed2.fo1());
        });

        execute_if(write_t3, [&]() {
            val<ENTRY_BITS> packed3 = concat(new_t3_counters.concat(), reg_tag3);
            t3.write(reg_idx3, packed3.fo1());
        });

        if constexpr (USE_BIAS) {
            execute_if(write_bias, [&]() {
                arr<val<2>, LI> new_bias_line = [&](u64 i) {
                    val<1> has_branch = val<1> { branch_mask >> i };
                    val<1> taken_bit = val<1> { taken_mask >> i };
                    val<2> orig_bias = reg_bias0[i];
                    orig_bias.fanout(hard<2> {});
                    val<2> bit_to_set = select(taken_bit, val<2> { 2 }, val<2> { 1 });
                    val<2> new_bias = orig_bias | bit_to_set;
                    return select(has_branch, new_bias, orig_bias.fo1());
                };
                bias_table.write(reg_idx_bias, new_bias_line.fo1());
            });
        }

        execute_if(performing_update_ghr, [&]() {
            ghr = new_ghr;
        });
    }
};

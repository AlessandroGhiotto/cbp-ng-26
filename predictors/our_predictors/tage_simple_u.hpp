#include "../../cbp.hpp"
#include "../../harcom.hpp"
#include <algorithm>

using namespace hcm;

/*
 * tage predictor.
 * - base_predictor: we index the PHT with the shifted PC (this is also used as predict1())
 * - full tage lookup: we have the tree of mux that selects the longest matching history
 *                      (this is used as predict2)
 *
 * additional features wrt basic version: utility bit, folded history
 */

template <
    u64 PC_B = 10,     // Number of index bits for the tables
    u64 TAG_B = 8,     // Number of bits for the tags
    u64 HIST_MAX = 64, // Max size of the Global History Register
    u64 L1 = 4,        // History length for Table 1 (Short)
    u64 L2 = 16,       // History length for Table 2 (Medium)
    u64 L3 = 64,       // History length for Table 3 (Long)
    u64 CTR_B = 3      // 3-bit counters are standard for TAGE tagged tables
    >
struct tage_simple_u : predictor
{
    static constexpr u64 PHT_ROWS = 1 << PC_B;
    static constexpr u64 ENTRY_BITS = CTR_B + TAG_B;

    // TABLES
    // T0 is the untagged base predictor (similar to a standard bimodal/gshare table)
    ram<val<CTR_B>, PHT_ROWS> t0;
    // T1, T2, T3 are the Tagged Components containing [Counter | Tag] packed together
    ram<val<ENTRY_BITS>, PHT_ROWS> t1;
    ram<val<ENTRY_BITS>, PHT_ROWS> t2;
    ram<val<ENTRY_BITS>, PHT_ROWS> t3;

    // RAMs for Useful Bits (u)
    ram<val<1>, PHT_ROWS> u1;
    ram<val<1>, PHT_ROWS> u2;
    ram<val<1>, PHT_ROWS> u3;

    // GHR
    reg<HIST_MAX> ghr;

    // Registers for Update Stage
    reg<CTR_B> final_counter;
    reg<CTR_B> alt_counter;
    reg<2> provider_id; // 0 = T0, 1 = T1, 2 = T2, 3 = T3

    reg<PC_B> reg_idx0, reg_idx1, reg_idx2, reg_idx3;
    reg<TAG_B> reg_tag1, reg_tag2, reg_tag3;
    reg<1> reg_u1, reg_u2, reg_u3;

    // Folded History Registers
    reg<PC_B> folded_idx1, folded_idx2, folded_idx3;
    reg<TAG_B> folded_tag1, folded_tag2, folded_tag3;

    val<CTR_B> update_counter(val<CTR_B> ctr, val<1> incr)
    {
        ctr.fanout(hard<2> {});
        val<CTR_B> increased = select(ctr == hard<ctr.maxval> {}, ctr, val<CTR_B> { ctr + 1 });
        val<CTR_B> decreased = select(ctr == hard<ctr.minval> {}, ctr, val<CTR_B> { ctr - 1 });
        return select(incr.fo1(), increased.fo1(), decreased.fo1());
    }

    template <u64 F, u64 L>
    val<F> get_next_folded(val<F> folded, val<1> taken, val<HIST_MAX> current_ghr)
    {
        folded.fanout(hard<2> {});
        val<F> rotated = (folded << 1) | (folded >> (F - 1));
        val<F> with_in = rotated ^ val<F> { taken };
        val<1> out_bit = val<1> { current_ghr >> (L - 1) };
        val<F> out_mask = val<F> { out_bit } << (L % F);
        return with_in ^ out_mask;
    }

    val<1> predict1(val<64> inst_pc)
    {
        inst_pc.fanout(hard<7> {});

        // GET INDEXES + TAGS
        // T0
        val<PC_B> idx0 = val<PC_B> { inst_pc >> 2 };
        reg_idx0 = idx0;

        // T1
        val<PC_B> idx1 = val<PC_B> { inst_pc >> 2 } ^ folded_idx1;
        val<TAG_B> tag1 = val<TAG_B> { inst_pc >> (2 + PC_B) } ^ folded_tag1;
        reg_idx1 = idx1;
        reg_tag1 = tag1;

        // T2
        val<PC_B> idx2 = val<PC_B> { inst_pc >> 2 } ^ folded_idx2;
        val<TAG_B> tag2 = val<TAG_B> { inst_pc >> (2 + PC_B) } ^ folded_tag2;
        reg_idx2 = idx2;
        reg_tag2 = tag2;

        // T3
        val<PC_B> idx3 = val<PC_B> { inst_pc >> 2 } ^ folded_idx3;
        val<TAG_B> tag3 = val<TAG_B> { inst_pc >> (2 + PC_B) } ^ folded_tag3;
        reg_idx3 = idx3;
        reg_tag3 = tag3;

        idx1.fanout(hard<2> {});
        idx2.fanout(hard<2> {});
        idx3.fanout(hard<2> {});

        // READS
        val<CTR_B> ctr0 = t0.read(idx0.fo1());

        val<ENTRY_BITS> raw1 = t1.read(idx1);
        val<ENTRY_BITS> raw2 = t2.read(idx2);
        val<ENTRY_BITS> raw3 = t3.read(idx3);

        // Split packed [Counter | Tag] fields
        auto [ctr1, stored_tag1] = split<CTR_B, TAG_B>(raw1.fo1());
        auto [ctr2, stored_tag2] = split<CTR_B, TAG_B>(raw2.fo1());
        auto [ctr3, stored_tag3] = split<CTR_B, TAG_B>(raw3.fo1());

        // Read useful bits
        val<1> u1_val = u1.read(idx1);
        val<1> u2_val = u2.read(idx2);
        val<1> u3_val = u3.read(idx3);

        reg_u1 = u1_val;
        reg_u2 = u2_val;
        reg_u3 = u3_val;

        // check hits
        val<1> hit1 = (L1 > 0) ? (stored_tag1 == tag1.fo1()) : val<1> { 0 };
        val<1> hit2 = (L2 > 0) ? (stored_tag2 == tag2.fo1()) : val<1> { 0 };
        val<1> hit3 = (L3 > 0) ? (stored_tag3 == tag3.fo1()) : val<1> { 0 };

        hit1.fanout(hard<2> {});
        hit2.fanout(hard<3> {});
        hit3.fanout(hard<4> {});

        // Longest-History Selection (Mux Cascade)
        final_counter = select(hit3, ctr3,
                               select(hit2, ctr2,
                                      select(hit1, ctr1, ctr0)));

        provider_id = select(hit3, val<2> { 3 },
                             select(hit2, val<2> { 2 },
                                    select(hit1, val<2> { 1 }, val<2> { 0 })));

        // Alternate Provider Selection
        alt_counter = select(hit3, select(hit2, ctr2, select(hit1, ctr1, ctr0)),
                             select(hit2, select(hit1, ctr1, ctr0),
                                    select(hit1, ctr0, ctr0)));

        // Return the MSB bit of the selected counter as the prediction
        final_counter.fanout(hard<2> {});
        return final_counter >> (CTR_B - 1);
    }

    val<1> predict2([[maybe_unused]] val<64> inst_pc)
    {
        return final_counter >> (CTR_B - 1);
    }

    void update_condbr([[maybe_unused]] val<64> branch_pc, val<1> taken, [[maybe_unused]] val<64> next_pc)
    {
        taken.fanout(hard<11> {});

        // Calculate the updated prediction state
        val<CTR_B> new_ctr = update_counter(final_counter, taken);
        new_ctr.fanout(hard<4> {});

        // Check if the prediction was wrong
        val<1> mispredicted = (final_counter >> (CTR_B - 1)) ^ taken;
        mispredicted.fanout(hard<7> {});

        // Pre-compute provider match flags
        val<1> is_p0 = (provider_id == hard<0> {});
        val<1> is_p1 = (provider_id == hard<1> {});
        val<1> is_p2 = (provider_id == hard<2> {});
        val<1> is_p3 = (provider_id == hard<3> {});

        is_p0.fanout(hard<7> {});
        is_p1.fanout(hard<7> {});
        is_p2.fanout(hard<5> {});
        is_p3.fanout(hard<3> {});

        val<1> counter_changed = (new_ctr != final_counter);
        counter_changed.fanout(hard<4> {});

        // Retrieve read useful bits
        val<1> u1_read = reg_u1;
        val<1> u2_read = reg_u2;
        val<1> u3_read = reg_u3;

        u1_read.fanout(hard<4> {});
        u2_read.fanout(hard<5> {});
        u3_read.fanout(hard<5> {});

        val<1> u123 = u1_read & u2_read & u3_read;
        u123.fanout(hard<3> {});

        // Allocation conditions
        val<1> alloc_t1 = mispredicted & is_p0 & ~u1_read;
        val<1> alloc_t2 = mispredicted & select(is_p0, u1_read & ~u2_read, is_p1 & ~u2_read);
        val<1> alloc_t3 = mispredicted & select(is_p0, u1_read & u2_read & ~u3_read,
                                                select(is_p1, u2_read & ~u3_read,
                                                       is_p2 & ~u3_read));

        // Decay conditions
        val<1> decay_t1_m = mispredicted & is_p0 & u123;
        val<1> decay_t2_m = mispredicted & select(is_p0, u123, is_p1 & u2_read & u3_read);
        val<1> decay_t3_m = mispredicted & select(is_p0, u123, select(is_p1, u2_read & u3_read, is_p2 & u3_read));

        alloc_t1.fanout(hard<3> {});
        alloc_t2.fanout(hard<3> {});
        alloc_t3.fanout(hard<3> {});
        decay_t1_m.fanout(hard<2> {});
        decay_t2_m.fanout(hard<2> {});
        decay_t3_m.fanout(hard<2> {});

        // Alternate prediction for utility tracking
        val<1> altpred = alt_counter >> (CTR_B - 1);
        val<1> pred = final_counter >> (CTR_B - 1);
        val<1> provider_useful = ~mispredicted & (pred != altpred);
        provider_useful.fanout(hard<3> {});

        // Define write conditions for RAM tables
        val<1> write_t0 = is_p0 & counter_changed;
        val<1> write_t1 = (is_p1 & counter_changed) | alloc_t1;
        val<1> write_t2 = (is_p2 & counter_changed) | alloc_t2;
        val<1> write_t3 = (is_p3 & counter_changed) | alloc_t3;

        // Define write conditions for Useful RAMs
        val<1> write_u1 = alloc_t1 | decay_t1_m | (is_p1 & provider_useful);
        val<1> write_u2 = alloc_t2 | decay_t2_m | (is_p2 & provider_useful);
        val<1> write_u3 = alloc_t3 | decay_t3_m | (is_p3 & provider_useful);

        write_t0.fanout(hard<2> {});
        write_t1.fanout(hard<2> {});
        write_t2.fanout(hard<2> {});
        write_t3.fanout(hard<2> {});
        write_u1.fanout(hard<2> {});
        write_u2.fanout(hard<2> {});
        write_u3.fanout(hard<2> {});

        // Notify simulator that memory writes are performing this cycle
        val<1> performing_update = write_t0 | write_t1 | write_t2 | write_t3 | write_u1 | write_u2 | write_u3;
        need_extra_cycle(performing_update);

        execute_if(write_t0, [&]() {
            t0.write(reg_idx0, new_ctr);
        });

        execute_if(write_t1, [&]() {
            val<CTR_B> ctr_t1 = select(is_p1, new_ctr, select(taken, val<CTR_B> { 4 }, val<CTR_B> { 3 }));
            val<ENTRY_BITS> packed1 = concat(ctr_t1, reg_tag1);
            t1.write(reg_idx1, packed1.fo1());
        });

        execute_if(write_t2, [&]() {
            val<CTR_B> ctr_t2 = select(is_p2, new_ctr, select(taken, val<CTR_B> { 4 }, val<CTR_B> { 3 }));
            val<ENTRY_BITS> packed2 = concat(ctr_t2, reg_tag2);
            t2.write(reg_idx2, packed2.fo1());
        });

        execute_if(write_t3, [&]() {
            val<CTR_B> ctr_t3 = select(is_p3, new_ctr, select(taken, val<CTR_B> { 4 }, val<CTR_B> { 3 }));
            val<ENTRY_BITS> packed3 = concat(ctr_t3, reg_tag3);
            t3.write(reg_idx3, packed3.fo1());
        });

        execute_if(write_u1, [&]() {
            val<1> val_u1 = select(alloc_t1 | decay_t1_m, val<1> { 0 }, val<1> { 1 });
            u1.write(reg_idx1, val_u1);
        });

        execute_if(write_u2, [&]() {
            val<1> val_u2 = select(alloc_t2 | decay_t2_m, val<1> { 0 }, val<1> { 1 });
            u2.write(reg_idx2, val_u2);
        });

        execute_if(write_u3, [&]() {
            val<1> val_u3 = select(alloc_t3 | decay_t3_m, val<1> { 0 }, val<1> { 1 });
            u3.write(reg_idx3, val_u3);
        });

        // Update Folded Histories
        folded_idx1 = get_next_folded<PC_B, L1>(folded_idx1, taken, ghr);
        folded_idx2 = get_next_folded<PC_B, L2>(folded_idx2, taken, ghr);
        folded_idx3 = get_next_folded<PC_B, L3>(folded_idx3, taken, ghr);

        folded_tag1 = get_next_folded<TAG_B, L1>(folded_tag1, taken, ghr);
        folded_tag2 = get_next_folded<TAG_B, L2>(folded_tag2, taken, ghr);
        folded_tag3 = get_next_folded<TAG_B, L3>(folded_tag3, taken, ghr);

        // Shift new direction into Global History Register
        ghr = (ghr << 1) + taken;
    }
    void update_cycle([[maybe_unused]] instruction_info& block_end_info) {}
    val<1> reuse_predict1([[maybe_unused]] val<64> inst_pc) { return val<1> { 0 }; }
    val<1> reuse_predict2([[maybe_unused]] val<64> inst_pc) { return val<1> { 0 }; }
};

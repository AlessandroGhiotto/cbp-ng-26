#include "../../cbp.hpp"
#include "../../harcom.hpp"
#include "../common.hpp"
#include <bit>

using namespace hcm;

/*
 * bimode_general implements the Bi-Mode++ subfamily of branch predictors.
 * By enabling or disabling template flags, it specializes into:
 * - bimode_fusion (uses majority vote transient state fusion)
 * - bimode_indx (uses BHR XOR for Choice PHT indexing)
 * - bimode_plus (uses bias table filtering)
 * - bimodepp (combination of all three enhancements + dynamic BHR selection)
 *
 * taken from "The Bimode++ Branch Predictor" paper
 */

template <
    u64 CHOICE_B = 10,          // log2 choice PHT size
    u64 BHR_B = 12,             // log2 branch history size
    u64 PHT_B = 10,             // log2 direction PHT size
    u64 CTR_B = 2,              // bits of saturating counters (normally 2)
    u64 BIAS_B = 11,            // log2 bias table size
    u64 CHOICE_BHR_B = 3,       // bits of BHR XORed into Choice PHT index (0 to disable)
    bool USE_FUSION = true,     // Enable transient state majority vote fusion
    bool USE_BIAS = true,       // Enable bias table filtering for extremely biased branches
    bool USE_DYNAMIC_BHR = true // Enable BHR selection (BHR_ALL / BHR_NOB)
    >
struct bimode_general : predictor
{
    static constexpr u64 CHOICE_ENTRIES = 1 << CHOICE_B;
    static constexpr u64 PHT_ENTRIES = 1 << PHT_B;
    static constexpr u64 BIAS_ENTRIES = 1 << BIAS_B;

    // Tables
    ram<val<CTR_B>, CHOICE_ENTRIES> choice_table;
    ram<val<CTR_B>, PHT_ENTRIES> taken_pht;
    ram<val<CTR_B>, PHT_ENTRIES> not_taken_pht;
    ram<val<2>, BIAS_ENTRIES> bias_table;

    // Registers to save state for update
    reg<CHOICE_B> choice_idx;
    reg<CTR_B> choice_ctr;
    reg<1> choice_val;

    reg<PHT_B> pht_idx;
    reg<CTR_B> taken_ctr;
    reg<CTR_B> not_taken_ctr;

    reg<BIAS_B> bias_idx;
    reg<2> bias_val;
    reg<2> reg_new_b_val;
    reg<1> reg_pred;

    // Branch History Registers
    reg<BHR_B> bhr_all;
    reg<BHR_B> bhr_nob;
    reg<4> bias_mod_cnt;

    val<1> predict1(val<64> inst_pc) override
    {
        inst_pc.fanout(hard<2> {});

        // Dynamic BHR Selection
        val<BHR_B> active_bhr = [&]() -> val<BHR_B> {
            if constexpr (USE_DYNAMIC_BHR)
            {
                val<1> select_all = (bias_mod_cnt == 15);
                return select(select_all, bhr_all, bhr_nob);
            }
            else
            {
                return bhr_all;
            }
        }();

        static constexpr u64 BHR_USES = 1 + (CHOICE_BHR_B > 0 ? 1 : 0) + (USE_BIAS ? 1 : 0);
        if constexpr (BHR_USES >= 2)
        {
            active_bhr.fanout(hard<BHR_USES> {});
        }

        // 1. Index Choice Table
        val<CHOICE_B> c_idx = [&]() {
            if constexpr (CHOICE_BHR_B > 0)
            {
                return val<CHOICE_B> { inst_pc >> 2 } ^ (val<CHOICE_B> { active_bhr } & val<CHOICE_B> { (1 << CHOICE_BHR_B) - 1 });
            }
            else
            {
                return val<CHOICE_B> { inst_pc >> 2 };
            }
        }();
        c_idx.fanout(hard<2> {});
        choice_idx = c_idx;

        val<CTR_B> c_ctr = choice_table.read(c_idx);
        c_ctr.fanout(hard<2> {});
        choice_ctr = c_ctr;

        // 2. Index Direction PHTs
        val<PHT_B> p_idx = [&]() {
            if constexpr (USE_BIAS)
            {
                return val<PHT_B> { inst_pc >> 2 } ^ val<PHT_B> { active_bhr };
            }
            else
            {
                return val<PHT_B> { inst_pc >> 2 } ^ val<PHT_B> { active_bhr };
            }
        }();
        p_idx.fanout(hard<2> {});
        pht_idx = p_idx;

        val<CTR_B> t_ctr = taken_pht.read(p_idx);
        t_ctr.fanout(hard<2> {});
        taken_ctr = t_ctr;

        val<CTR_B> nt_ctr = not_taken_pht.read(p_idx.fo1());
        nt_ctr.fanout(hard<2> {});
        not_taken_ctr = nt_ctr;

        // 3. Index Bias Table
        if constexpr (USE_BIAS)
        {
            val<BIAS_B> b_idx = val<BIAS_B> { inst_pc >> 2 } ^ val<BIAS_B> { active_bhr };
            bias_idx = b_idx;

            val<2> b_val = bias_table.read(b_idx);
            bias_val = b_val;
        }

        // Compute individual predictions
        val<1> c_pred = c_ctr >> (CTR_B - 1);
        choice_val = c_pred;

        // 4. Fusion Function Logic
        val<1> bimode_pred = [&]() {
            if constexpr (USE_FUSION)
            {
                c_pred.fanout(hard<5> {});
                val<1> t_pred = t_ctr >> (CTR_B - 1);
                t_pred.fanout(hard<3> {});
                val<1> nt_pred = nt_ctr >> (CTR_B - 1);
                nt_pred.fanout(hard<3> {});

                val<CTR_B> selected_ctr = select(c_pred, t_ctr.fo1(), nt_ctr.fo1());
                val<1> selected_pred = select(c_pred, t_pred, nt_pred);

                val<1> is_transient = (selected_ctr == 1) | (selected_ctr == 2);
                val<1> term1 = c_pred & t_pred;
                val<1> term2 = t_pred.fo1() & nt_pred;
                val<1> term3 = c_pred.fo1() & nt_pred.fo1();
                val<1> majority_pred = term1 | term2 | term3;

                return select(is_transient, majority_pred, selected_pred);
            }
            else
            {
                c_pred.fanout(hard<2> {});
                return select(c_pred.fo1(), t_ctr.fo1(), nt_ctr.fo1()) >> (CTR_B - 1);
            }
        }();

        // 5. Predict using Bias Table if entry is still biased
        val<1> pred = [&]() {
            if constexpr (USE_BIAS)
            {
                val<2> b_val = bias_val;
                val<1> untaken_biased = ~(b_val >> 1);
                val<1> taken_biased = ~(b_val & 1);
                untaken_biased.fanout(hard<2> {});

                return select(untaken_biased, val<1> { 0 }, select(taken_biased, val<1> { 1 }, bimode_pred.fo1()));
            }
            else
            {
                return bimode_pred;
            }
        }();
        pred.fanout(hard<2> {});
        reg_pred = pred;

        return pred;
    }

    val<1> predict2([[maybe_unused]] val<64> inst_pc) override
    {
        return reg_pred;
    }

    void update_condbr([[maybe_unused]] val<64> branch_pc, val<1> taken, [[maybe_unused]] val<64> next_pc) override
    {
        static constexpr u64 TAKEN_USES = 4 + (USE_BIAS ? 1 : 0) + (USE_DYNAMIC_BHR ? 1 : 0);
        taken.fanout(hard<TAKEN_USES> {});

        // 1. Bias table updates
        val<1> update_bias = [&]() {
            if constexpr (USE_BIAS)
            {
                val<2> bit_to_set = select(taken, val<2> { 2 }, val<2> { 1 });
                val<2> new_b_val = bias_val | bit_to_set;
                new_b_val.fanout(hard<2> {});

                val<1> bias_modified = (new_b_val != bias_val);
                static constexpr u64 BIAS_MOD_USES = USE_DYNAMIC_BHR ? 3 : 2;
                bias_modified.fanout(hard<BIAS_MOD_USES> {});

                if constexpr (USE_DYNAMIC_BHR)
                {
                    val<4> new_bias_mod_cnt = select(bias_modified,
                                                     select(bias_mod_cnt == 15, bias_mod_cnt, val<4> { bias_mod_cnt + 1 }),
                                                     bias_mod_cnt);
                    bias_mod_cnt = new_bias_mod_cnt;
                }

                reg_new_b_val = new_b_val.fo1();

                return bias_modified.fo1();
            }
            else
            {
                return val<1> { 0 };
            }
        }();
        update_bias.fanout(hard<2> {});

        // 2. Choice and Direction PHT updates
        val<1> use_bimode_pred = [&]() {
            if constexpr (USE_BIAS)
            {
                return val<1> { bias_val == val<2> { 3 } };
            }
            else
            {
                return val<1> { 1 };
            }
        }();

        static constexpr u64 BIMODE_PRED_USES = USE_DYNAMIC_BHR ? 4 : 3;
        use_bimode_pred.fanout(hard<BIMODE_PRED_USES> {});

        val<CTR_B> new_choice_ctr = update_ctr(choice_ctr, taken);
        new_choice_ctr.fanout(hard<2> {});
        val<1> update_choice = use_bimode_pred & (new_choice_ctr != choice_ctr);

        val<CTR_B> new_taken_ctr = update_ctr(taken_ctr, taken);
        new_taken_ctr.fanout(hard<2> {});
        val<1> update_taken = use_bimode_pred & choice_val & (new_taken_ctr != taken_ctr);

        val<CTR_B> new_not_taken_ctr = update_ctr(not_taken_ctr, taken);
        new_not_taken_ctr.fanout(hard<2> {});

        val<1> update_not_taken = [&]() {
            if constexpr (USE_DYNAMIC_BHR)
            {
                return use_bimode_pred & ~choice_val & (new_not_taken_ctr != not_taken_ctr);
            }
            else
            {
                return use_bimode_pred & ~choice_val & (new_not_taken_ctr != not_taken_ctr);
            }
        }();

        // SRAM write extra cycle check
        val<1> extra_c = [&]() {
            if constexpr (USE_BIAS)
            {
                return update_choice | update_taken | update_not_taken | update_bias;
            }
            else
            {
                return update_choice | update_taken | update_not_taken | update_bias.fo1();
            }
        }();
        need_extra_cycle(extra_c.fo1());

        // Perform SRAM writes
        execute_if(update_choice.fo1(), [&]() {
            choice_table.write(choice_idx, new_choice_ctr.fo1());
        });

        execute_if(update_taken.fo1(), [&]() {
            taken_pht.write(pht_idx, new_taken_ctr.fo1());
        });

        execute_if(update_not_taken.fo1(), [&]() {
            not_taken_pht.write(pht_idx, new_not_taken_ctr.fo1());
        });

        if constexpr (USE_BIAS)
        {
            execute_if(update_bias.fo1(), [&]() {
                bias_table.write(bias_idx, reg_new_b_val);
            });
        }

        // 5. Update BHR registers
        if constexpr (USE_DYNAMIC_BHR)
        {
            bhr_all = (bhr_all << 1) + taken;
            val<BHR_B> next_bhr_nob = select(use_bimode_pred.fo1(), val<BHR_B> { (bhr_nob << 1) + taken.fo1() }, bhr_nob);
            bhr_nob = next_bhr_nob;
        }
        else
        {
            bhr_all = (bhr_all << 1) + taken.fo1();
        }
    }

    void update_cycle([[maybe_unused]] instruction_info& block_end_info) override
    {
    }

    val<1> reuse_predict1([[maybe_unused]] val<64> inst_pc) override
    {
        return hard<0> {};
    }

    val<1> reuse_predict2([[maybe_unused]] val<64> inst_pc) override
    {
        return hard<0> {};
    }
};

// Specialized Predictor Classes
template <u64 CHOICE_B = 10, u64 BHR_B = 12, u64 PHT_B = 10, u64 CTR_B = 2>
struct bimode_fusion : bimode_general<CHOICE_B, BHR_B, PHT_B, CTR_B, 1, 0, true, false, false>
{
    using bimode_general<CHOICE_B, BHR_B, PHT_B, CTR_B, 1, 0, true, false, false>::bimode_general;
};

template <u64 CHOICE_B = 10, u64 BHR_B = 12, u64 PHT_B = 10, u64 CTR_B = 2, u64 CHOICE_BHR_B = 3>
struct bimode_indx : bimode_general<CHOICE_B, BHR_B, PHT_B, CTR_B, 1, CHOICE_BHR_B, false, false, false>
{
    using bimode_general<CHOICE_B, BHR_B, PHT_B, CTR_B, 1, CHOICE_BHR_B, false, false, false>::bimode_general;
};

template <u64 CHOICE_B = 10, u64 BHR_B = 12, u64 PHT_B = 10, u64 CTR_B = 2, u64 BIAS_B = 11>
struct bimode_plus : bimode_general<CHOICE_B, BHR_B, PHT_B, CTR_B, BIAS_B, 0, false, true, false>
{
    using bimode_general<CHOICE_B, BHR_B, PHT_B, CTR_B, BIAS_B, 0, false, true, false>::bimode_general;
};

template <u64 CHOICE_B = 10, u64 BHR_B = 12, u64 PHT_B = 10, u64 CTR_B = 2, u64 BIAS_B = 11, u64 CHOICE_BHR_B = 3>
struct bimodepp : bimode_general<CHOICE_B, BHR_B, PHT_B, CTR_B, BIAS_B, CHOICE_BHR_B, true, true, true>
{
    using bimode_general<CHOICE_B, BHR_B, PHT_B, CTR_B, BIAS_B, CHOICE_BHR_B, true, true, true>::bimode_general;
};

#include "../../cbp.hpp"
#include "../../harcom.hpp"

using namespace hcm;

template <u64 PHT_INDEX_B = 10, u64 HIST_B = 8, u64 CTR_B = 2>
struct gag_exp : predictor
{
    static constexpr u64 PHT_ROWS = 1 << PHT_INDEX_B;
    ram<val<CTR_B>, PHT_ROWS> counters;
    reg<CTR_B> counter;
    reg<HIST_B> bhr;

    val<PHT_INDEX_B> get_index(val<64> inst_pc, val<HIST_B> current_bhr)
    {
        current_bhr.fanout(hard<2>{});
        if constexpr (HIST_B == PHT_INDEX_B) {
            return val<PHT_INDEX_B>{ current_bhr };
        } else if constexpr (HIST_B < PHT_INDEX_B) {
            constexpr u64 PC_PADDING_B = PHT_INDEX_B - HIST_B;
            val<PC_PADDING_B> pc_part = val<PC_PADDING_B>{ inst_pc >> 2 };
            return concat(pc_part, current_bhr);
        } else {
            return current_bhr.fo1().make_array(val<PHT_INDEX_B>{}).fold_xor();
        }
    }

    val<1> predict1([[maybe_unused]] val<64> inst_pc)
    {
        val<PHT_INDEX_B> index = get_index(inst_pc, bhr);
        counter = counters.read(index.fo1());
        return counter >> (counter.size - 1);
    };

    val<1> predict2([[maybe_unused]] val<64> inst_pc)
    {
        return counter >> (counter.size - 1);
    }

    inline val<CTR_B> update_counter(val<CTR_B> ctr, val<1> incr)
    {
        ctr.fanout(hard<6> {});
        val<CTR_B> increased = select(ctr == hard<ctr.maxval> {}, ctr, val<CTR_B> { ctr + 1 });
        val<CTR_B> decreased = select(ctr == hard<ctr.minval> {}, ctr, val<CTR_B> { ctr - 1 });
        return select(incr.fo1(), increased.fo1(), decreased.fo1());
    }

    void update_condbr([[maybe_unused]] val<64> branch_pc, [[maybe_unused]] val<1> taken, [[maybe_unused]] val<64> next_pc)
    {
        taken.fanout(hard<2> {});
        bhr.fanout(hard<3> {});
        
        val<HIST_B> old_bhr = bhr;
        bhr = (bhr << 1) + taken;

        val<CTR_B> newcounter = update_counter(counter, taken);
        val<1> performing_update = val<1> { newcounter != counter };

        need_extra_cycle(performing_update);

        execute_if(performing_update, [&]() {
            val<PHT_INDEX_B> index = get_index(branch_pc.fo1(), old_bhr.fo1());
            counters.write(index.fo1(), newcounter);
        });
    }

    void update_cycle([[maybe_unused]] instruction_info& block_end_info)
    {
    }

    val<1> reuse_predict1([[maybe_unused]] val<64> inst_pc)
    {
        return hard<0> {};
    };
    val<1> reuse_predict2([[maybe_unused]] val<64> inst_pc)
    {
        return hard<0> {};
    }
};

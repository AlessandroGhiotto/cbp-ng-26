# NOTES AleGhi

```bash
./compile cbp -DPREDICTOR="tutorial_00"
./compile cbp -DPREDICTOR="my_predictor<>"
./cbp ./gcc_test_trace.gz gcc_test_trace 0 40000 --format human
```

### The Predictor class

1. For each prediction block, at the first instruction we run `predict1()` and `predict2()`. If it's not the first instruction we call `reuse_predict1()` and `reuse_predict2()`.
1. Then we `update_condbr()` if the instruction was a conditional branch
1. If one of the following condition is satisfied:
   - the instruction was a taken branch
   - we have a misprediction
   - we call `reuse_prediction(0)`

   Then we call `update_cycle()` and start the next prediction block. Otherwise we go to the next instruction (and call `reuse_predict()`)

**Two level predictor**: `predict1()` is faster and less accurate, we increase throughput by starting the next instruction already after predict1 (which is fast). Than we are going to correct the prediction with `predict2()`, which is more accurate and expensive. It's used to have an earlier correction, so that we don't waste x cycles till we reach the actual computation of the branch. (later we will actually compute the branch and see if the second prediction was correct)

**reuse_predict**: `predict()` methods are more expensive and called only at the beginning of the prediction block, `reuse_predict()` instead are cheaper. This allows to setup the context only once, and than reuse it for all the instructions in the same block (instructions in the same block share the context!).
The predictor itself can decide the prediction block length, by calling `reuse_prediction(0)`.

### HARCOM datatypes

- **VAL**: a intermidiate value with a particular type and bit width
- **HARD**: acts as a hardware parameter/constant, and the template parameter is its value
- **REG**: unlike vals, regs may be updated (although they may only be written once per
  cycle). They can be used to persist information between cycles/calls.
- **RAM**: SRAM for storing info that is too much for the reg, can only perform
  one read OR one write per cycle

### Features

- `make_array(val<6>{})` chunks the 64-bit `inst_pc` into a HARCOM `arr` made up of 6-bit `val`s.
- `fold_xor()`, uses a series of exclusive-or operations to combine all of the 6-bit `val`s in the `arr` into a single 6-bit index.
- RAM can't be Read and Written in the same clock cycle! `need_extra_cycle(bool)` tells that the predictor needs an additional cycle (if bool == 1). This can be combined with `execute_if()`
  ```cpp
  need_extra_cycle(label);
  // Update the SRAM array conditionally
  execute_if(label, [&]() {...});
  ```

### fanout

Reading an unnamed value (aka rvalue) incurs no hardware cost, as it is known at compile
time that such value will be read only once. However, it is not known at compile time how
many times a named value (aka lvalue) is read. To make the delay of reading a named value
logarithmic instead of linear, the HARCOM user must use the fanout function:

```cpp
val <4 > x = 1;
x . fanout ( hard <8 >{}); // make delay logarithmic
arr < val <1 > ,8 > A = x . replicate ( hard <8 >{});
A . print ();
```

If the value is actually read more than what was promised with the fanout function, no error
is triggered. Instead, the read delay simply grows linearly after the initial logarithmic growth.

**PRACTICAL GUIDE:**

- fanout on registers is useless
- for array, if we access a val/arr N times (1 per array value), it counts N.
- for array, if we access via a for loop/lambda function all the values once, it counts 1.
- The condition of an execute_if has an implicit fanout consisting of as many reads as the
  number of conditional register writes and conditional RAM writes, plus one implicit read if the
  execute_if outputs a value.

Example:

```cpp
arr<val<CTR_B>, LI> new_counters = [&](u64 i) {
    return select(val<1> { update_mask >> i },
                  update_counter(counter[i], val<1> { taken_mask >> i }),
                  counter[i]);
};
```

assume that `update_mask`, `taken_mask`, `counter` are just values/arr (not registers). in this case `update_mask` and `taken_mask` needs a funout of N (N=LI in this case), since it is accessed as a whole N times. Instead counter needs a fanout of 1, since it is accessed once per value.

### fo1

Whenever possible, transient values (vals) that are read only once should remain unnamed.
Nevertheless, for program readability, the HARCOM user may wish to give a name to a val
even though it is read only once. In this situation, if the read delay is deemed non-negligible, it
is possible to use function fo1 to "unname" a named value:

```cpp
val <4 > x = 1;
arr < val <1 > ,8 > A = x . fo1 (). replicate ( hard <8 >{});
A . print ();
// ( x +1). print (); // error !
```

Trying to re-read a value after it has been read through fo1 triggers an error at execution.

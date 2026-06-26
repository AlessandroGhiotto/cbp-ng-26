#include "../../harcom.hpp"

using namespace hcm; // HARCOM namespace

int main()
{
    reg<2> counter0 { 0b00 };
    reg<2> counter1 { 0b01 };
    reg<2> counter2 { 0b10 };
    reg<2> counter3 { 0b11 };

    // arr<reg<2>, 4> counters = [](u64 i) { return i + 1; };
    counter0.print("c0: ");  // 00
    (counter0 >> 1).print(); // 00
    std::cout << std::endl;

    counter1.print("c1: ");  // 01
    (counter1 >> 1).print(); // 00
    std::cout << std::endl;

    counter2.print("c2: ");  // 10
    (counter2 >> 1).print(); // 01
    std::cout << std::endl;

    counter3.print("c3: ");  // 11
    (counter3 >> 1).print(); // 01
    std::cout << std::endl;

    return 0;
}

/* COMPILING
 * g++ -std=c++20 -o cbp predictors/tutorial/testPipeOperator.cpp
 * ./cbp

c0: 0 (t=0 ps, loc=0)
0 (t=4 ps, loc=0)

c1: 1 (t=0 ps, loc=0)
0 (t=4 ps, loc=0)

c2: 2 (t=0 ps, loc=0)
1 (t=4 ps, loc=0)

c3: 3 (t=0 ps, loc=0)
1 (t=4 ps, loc=0)

*/

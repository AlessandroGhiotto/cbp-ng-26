#include "predictors/always_taken.hpp"
#include "predictors/bimodal.hpp"
#include "predictors/bimodalN.hpp"
#include "predictors/gshare.hpp"
#include "predictors/gshareN.hpp"
#include "predictors/gshareN_ahead.hpp"
#include "predictors/hashed_perceptron.hpp"
#include "predictors/lxor.hpp"
#include "predictors/never_taken.hpp"
#include "predictors/our_predictors/our_predictors.hpp"
#include "predictors/perceptron.hpp"
#include "predictors/tage.hpp"
#include "predictors/tutorial/tutorial.hpp"

#ifdef PREDICTOR
using branch_predictor = PREDICTOR;
#else
// using branch_predictor = bimodal<>;
// using branch_predictor = gshare<>;
using branch_predictor = tage<>;
#endif

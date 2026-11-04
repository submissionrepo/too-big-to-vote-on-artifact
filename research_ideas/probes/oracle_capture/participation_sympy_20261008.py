"""Theorem 4 (iv) and Corollary 1 with participation pi (2026-10-08), first layer, sympy.
(a) Corollary 1, impossibility: honest hF = hT = mu pi and a coalition of (1 - 2 mu) pi move F's payout from
    rho(mu) = 0 to rho(1 - mu) = 1; holding Q shares the coalition nets Q - delta (1 - 2 mu) pi V.
(b) Theorem 4 (iv): with pi <= pi_j for every market j of a round and Q_j <= OI_j, the gain bound
    sigma sum_j Q_j / (pi_j (1 - 2 mu)) is at most sigma sum_j OI_j / (pi (1 - 2 mu)), and the cost delta sigma V minus
    that bound equals sigma (delta (1 - 2 mu) pi V - sum_j OI_j) / (pi (1 - 2 mu)).
(c) Theorem 4 (i): the payout range width rho((hF + s)/pi) - rho(hF/pi) is at most s / (pi (1 - 2 mu)) (rho is
    1/(1 - 2 mu)-Lipschitz), equality on the ramp; at pi = 1 it is the full-participation bound.
(d) Per coalition versus every coalition: pi = P + s >= P for honest participation P, so OI <= delta (1 - 2 mu) P V
    implies OI <= delta (1 - 2 mu) pi V.
"""
import json
import os
import sympy as sp

HERE = os.path.dirname(os.path.abspath(__file__))
mu, pi, s, hF, hT, Q, d, V, P = sp.symbols("mu pi s h_F h_T Q delta V P", positive=True)
out = {}

ramp = lambda f: (f - mu) / (1 - 2 * mu)
# (a)
el_hF = mu * pi
coal = (1 - 2 * mu) * pi
lo = el_hF / (el_hF + el_hF + coal)
hi = (el_hF + coal) / (el_hF + el_hF + coal)
out["a_lo_is_mu"] = sp.simplify(lo - mu) == 0
out["a_hi_is_1_minus_mu"] = sp.simplify(hi - (1 - mu)) == 0
out["a_ramp_lo_zero"] = sp.simplify(ramp(lo)) == 0
out["a_ramp_hi_one"] = sp.simplify(ramp(hi) - 1) == 0
out["a_net"] = str(sp.simplify(Q - d * coal * V))
out["a_net_is_Q_minus_limit"] = sp.simplify((Q - d * coal * V) - (Q - d * (1 - 2 * mu) * pi * V)) == 0

# (b) two markets with participations pi1, pi2 >= pi and Q_j <= OI_j
pi1, pi2, O1, O2, Q1, Q2 = sp.symbols("pi_1 pi_2 OI_1 OI_2 Q_1 Q_2", positive=True)
gain = s * (Q1 / pi1 + Q2 / pi2) / (1 - 2 * mu)
bound = s * (O1 + O2) / (pi * (1 - 2 * mu))
# substitute pi_j = pi + e_j, OI_j = Q_j + g_j with e_j, g_j >= 0 and check bound - gain >= 0 term by term
e1, e2, g1, g2 = sp.symbols("e_1 e_2 g_1 g_2", nonnegative=True)
diff = sp.together((bound - gain).subs({pi1: pi + e1, pi2: pi + e2, O1: Q1 + g1, O2: Q2 + g2}))
num, den = sp.fraction(diff)
num = sp.expand(num)
out["b_bound_minus_gain_numerator_coeffs_nonnegative"] = all(c >= 0 for c in sp.Poly(num, e1, e2, g1, g2, s, Q1, Q2, pi).coeffs()) if (1 - 2 * mu) != 0 else None
out["b_den"] = str(sp.factor(den))
cost_minus_bound = sp.simplify(d * s * V - bound - s * (d * (1 - 2 * mu) * pi * V - (O1 + O2)) / (pi * (1 - 2 * mu)))
out["b_cost_minus_bound_identity"] = cost_minus_bound == 0

# (c)
width = ramp((hF + s) / (hF + hT + s)) - ramp(hF / (hF + hT + s))
out["c_width_identity"] = sp.simplify(width - s / ((hF + hT + s) * (1 - 2 * mu))) == 0

# (d)
out["d_implication"] = sp.simplify((d * (1 - 2 * mu) * (P + s) * V) - (d * (1 - 2 * mu) * P * V) - d * (1 - 2 * mu) * s * V) == 0

out["all_pass"] = all(v is True for k, v in out.items() if isinstance(v, bool))
json.dump(out, open(os.path.join(HERE, "data", "participation_sympy_20261008.json"), "w"), indent=1)
print(json.dumps(out, indent=1))

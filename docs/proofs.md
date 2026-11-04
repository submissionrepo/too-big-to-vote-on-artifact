# Supplementary proofs

These are the five proofs referred to the artifact in the paper, with the coalition symbol sigma of the current paper; the proofs of Propositions 3 and 4 and of Theorem 2 were revised on 2026-10-09 after an independent audit. They carry no new verification credential. The remaining proofs appear in the included manuscript.

Notation: $S$ is total stake, $\sigma$ the coalition share, $h_F$ and $h_T$ the honest shares, $\theta$ the strict resolution threshold, $\lambda$ the common penalty rate, $\mu$ the fallback parameter, and $\widehat p$ the reference price of an $F$ share.

## Proposition 1: Stall is free

We need every answer to stay below the line in every round, and we need the coalition to pay nothing for it. The second part is a reading of the contract: penalties are computed only when a resolved request is processed, so a request that rolls until deletion never charges anyone, and the coalition's stake keeps earning emissions meanwhile. For the first part, if the coalition abstains, every answer's share $x_b$ is bounded by the votes cast,
$$
x_b \;\le\; 1 - \sigma \;\le\; \theta .
$$

## Proposition 2: The penalty pays the winner

We only have to count the pool. It is $\lambda$ times the stake that did not vote for $b^{*}$, which is $\lambda(S - v^{*})$, and it is divided among the $v^{*}$ winning tokens, so each winning token receives $\lambda(S - v^{*})/v^{*}$ and a coalition's $\sigma S$ winning tokens receive
$$
\sigma S \cdot \frac{\lambda (S - v^{*})}{v^{*}} = \frac{\sigma S}{v^{*}}\,\lambda (S - v^{*}) .
$$

## Proposition 3: The narrow-coalition premium

The idea is that a vote for $b$ is a bet that pays the pool's rate when $b$ wins and costs $\lambda$ otherwise, and the pool's rate falls with the size of the winning side. The voter is risk-neutral, so it ranks actions by expected transfer, and nonpivotal, so the probabilities below do not depend on its vote. Write $p_b$ for the probability that $b$ resolves, $p_\emptyset$ for the probability of a roll, and $\lambda_w, \lambda_n$ for the penalties on a wrong vote and on absence (both $\lambda$ today). Per token, voting $b$ yields
$$
\begin{aligned}
U_b &= p_b\,\mathbb{E}\!\left[\frac{\lambda_w (v - v(b)) + \lambda_n (S - v)}{v(b)} \,\Big|\, b\right] \\
    &\qquad - \lambda_w\,(1 - p_b - p_\emptyset),
\end{aligned}
$$
where $v$ is the total vote and a term with $p_b = 0$ is read as zero. We compare two answers: the terms $-\lambda_w(1 - p_\emptyset)$ cancel, and with $R_b = \mathbb{E}[(\lambda_w v + \lambda_n (S - v))/v(b) \mid b]$ what remains is
$$
U_b - U_c = p_b R_b - p_c R_c ,
$$
which with $\lambda_w = \lambda_n$ is $\lambda\,(p_b\,\mathbb{E}[S/v(b)\mid b] - p_c\,\mathbb{E}[S/v(c) \mid c])$. The swing $\lambda S/v(b)$ per token between a winning and a losing vote is the pool reward $\lambda(S - v(b))/v(b)$ plus the penalty $\lambda$ avoided; since a resolving $v(b)$ lies between $\theta S$ and $S$, $S/v(b)$ lies in $[1, 1/\theta)$, so the swing in a narrow win is up to $1/\theta$ times that in a landslide. Against abstention, $U_b - U_\emptyset = p_b\,\mathbb{E}[\,\text{pool rate} + \lambda_w \mid b\,] - (\lambda_w - \lambda_n)(1 - p_\emptyset)$, which with $\lambda_w = \lambda_n$ is $\lambda p_b\,\mathbb{E}[S/v(b) \mid b] \ge \lambda p_b > 0$ whenever $p_b > 0$.

## Theorem 2: The threshold window

We fix the honest electorate: the block $h_F$ votes $F$ and the remaining $1 - \sigma - h_F$ votes $T$. Capture is Theorem 1 (Capture), because the honest response is the one worst for the coalition. To block, the coalition abstains; $T$'s tally is then $1 - \sigma - h_F$ and $F$'s is $h_F$, so, as $h_F \le \theta$ keeps $F$ below the line, the question rolls exactly when $1 - \sigma - h_F \le \theta$. Both attacks fail for the $\theta$ with $\sigma \le \theta - h_F$ and $\sigma < 1 - \theta - h_F$, that is for
$$
\theta \in [\sigma + h_F,\; 1 - \sigma - h_F), \qquad\text{non-empty iff } \sigma + h_F < \tfrac12 .
$$

## Proposition 4: What the fallback guarantees

We read the definition of $F_\mu$ with the margin measured against votes cast, $\mu < 1 - \theta$ so that $1 - \mu > \theta$, full participation, $h_F \le \mu$ and $\widehat p < 1$; the honest $T$ block is $h_T = 1 - \sigma - h_F$. With the coalition's stake split into $a$ for $F$, $b$ for $T$ and $c$ abstaining, the votes cast are $1 - c$, and $F$'s share of them is $(h_F + a)/(1 - c) \le h_F + \sigma$, because $h_F + \sigma \le 1$; voting $F$ with everything attains $h_F + \sigma$. (i) With $\widehat p < 1$ only a clear resolution to $F$, a share of at least $1 - \mu$ of the votes cast, pays $F$ a dollar; it needs $h_F + \sigma \ge 1 - \mu$, and voting $F$ then resolves $F$, as $1 - \mu > \theta$. (ii) If $\sigma \le \mu - h_F$, the stake $1 - \sigma - h_F + b \ge 1 - \mu > \theta$ voting $T$ resolves $T$ whatever the coalition does, with at least $1 - \sigma - h_F \ge 1 - \mu$ of the votes cast, so $T$ is paid in full. If $\mu - h_F < \sigma < 1 - \theta - h_F$, voting $F$ resolves $T$ with the share $1 - \sigma - h_F < 1 - \mu$ of the votes cast, and the reference price is paid. If $\sigma \ge 1 - \theta - h_F$, we give $T$ a stake $b$ with $1 - \sigma - h_F + b$ strictly between $\theta$ and $1 - \mu$ and $F$ the rest; such a $b \in [0, \sigma]$ exists because $1 - \sigma - h_F \le \theta$ and $1 - h_F \ge 1 - \mu$, and $T$ then resolves with less than $1 - \mu$ of the votes cast. (iii) The two requirements sum to $1 - 2h_F$. (iv) Below $1 - \mu - h_F$ neither $F$ nor the $0.5$ answer can reach $1 - \mu$ of the votes cast, the latter because a stake $c' \le \sigma$ given to it holds at most $c'/(1 - \sigma + c') < 1 - \mu$ of them; so the question pays either as the honest vote says, one to $T$ and zero to $F$, or the reference price, $1 - \widehat p$ to $T$ and $\widehat p$ to $F$, every share's payout moves by at most $\widehat p$, and an $F$ share bought at $\bar p$ returns at most
$$
\widehat p - \bar p .
$$

## Computational evidence

`capture_probe.py` E7 is the noisy-coordination-game numerical probe mentioned in the paper. Its floating-point fixed points are discovery evidence. The exact and symbolic scripts have their scope and historical status in `docs/computational_evidence.md`.

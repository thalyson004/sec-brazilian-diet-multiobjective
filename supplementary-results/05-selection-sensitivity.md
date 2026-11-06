# S5. Reference-based selection sensitivity

[Supplementary results](README.md)

The front-restricted sensitivity asks whether joint gains were available without recovering candidates discarded from the final reporting fronts. It keeps one choice per run where possible and uses the observed profile means $\bar A_p$, $\bar C_p$, $\bar W_p$ and $\bar D_p$. The departure references, calculated from individual observed days, are 186.19%, 206.13%, 178.78% and 200.33% for F30, F60, M30 and M60.

The front-restricted maximin sensitivity first retains menus satisfying $A>\bar A_p$, $C<\bar C_p$ and $W<\bar W_p$; the four-outcome variant also requires $D<\bar D_p$. Within this eligible set it maximizes the smallest dimensionless gain: $(A-\bar A_p)/(100-\bar A_p)$ for attainment and $(\bar j_p-j)/\bar j_p$ for each protected outcome $j\in\{C,W,D\}$. Equal minimum gains are resolved by larger total gain, then smaller original candidate identifier. This is an explicit retrospective preference rule. The $10^{-12}$ comparison tolerance handles floating-point equality, not clinically meaningful differences. If no eligible menu exists, the rule reports an absent selection and does not substitute a worsening menu.

For an outcome minimized by the decision maker, an independent coordinate-wise bound is obtained by taking its minimum in each run front $F_{pr}$. In particular,

$$
L_{W,p}=\frac{1}{480}\sum_{r=1}^{480}\min_{x\in F_{pr}}W(x).
$$

Every one-menu-per-run selection with the original equal weights has mean water at least $L_{W,p}$. Table [S10](#table-s10) shows why post-selection cannot reduce mean water in all profiles: F30 and M60 already exceed their observed references at this lower bound. This statement concerns the retained fronts, not the full feasible meal-combination space.

<a id="table-s10"></a>

**Table S10.** Post-selection limits and availability of joint improvements on the saved reporting fronts. Water values are mean L/day. Min. W independently selects the lowest-water member of each run front, providing a lower bound for any one-menu-per-run selection. $\Delta$ compares that bound with the observed mean. Joint NCW and NCWD count fronts with simultaneous improvement over the profile observed means in the corresponding physical outcomes; these are protected outcomes, not new search scenarios. GLOBAL averages profile means equally and sums counts.

| Profile | Observed W | Comp. W | Min. W | $\Delta$ (%) | Joint NCW | Joint NCWD |
| --- | --- | --- | --- | --- | --- | --- |
| F30 | 5262.0 | 6379.4 | 5487.5 | +4.29 | 216/480 | 23/480 |
| F60 | 5704.9 | 5921.0 | 5612.9 | -1.61 | 287/480 | 188/480 |
| M30 | 6143.8 | 4560.9 | 3168.7 | -48.42 | 451/480 | 277/480 |
| M60 | 6622.6 | 7744.9 | 6675.0 | +0.79 | 248/480 | 147/480 |
| GLOBAL | 5933.3 | 6151.6 | 5236.0 | -11.75 | 1202/1920 | 635/1920 |

[Download CSV](tables/table-s10.csv)

Using all four coordinates in the ideal distance gives mean water of 5674.4, 5829.9, 3372.4 and 6799.9 L/day in F30, F60, M30 and M60. Water remains above the observed mean in three profiles. Joint NCW gains are available on 1202 of the 1920 final fronts, and joint NCWD gains on 635. Conditional summaries of eligible fronts have a different algorithm–scenario mixture and cannot replace the balanced 480-selection profile summaries. The Ref. results in the main text use complete candidate histories instead, recovering an eligible choice in every run.

Joint NCW improvement is present in 834 of the 960 runs whose search objectives include water, compared with 368 of the 960 runs omitting it. This descriptive contrast helps explain the heterogeneous coverage. It does not isolate a causal effect of including water because the paired or tripled objective sets also differ in their other coordinates.

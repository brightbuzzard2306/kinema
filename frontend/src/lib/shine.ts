/**
 * Timing shared by every looping ShinyText on the home page (the "tonight?" headline and the prompt placeholder).
 * Same speed + same delay + `sync` (one shared clock) = the glint crosses both texts at the same moments, at the same fraction of their width.
 * Change it here and both follow.
 */
// travel = 3 is the headline's natural path (its glint is a thin line), so the headline looks exactly as before.
export const SHINE_TIMING = { speed: 3.4, delay: 0.6, sync: true, travel: 3 } as const;

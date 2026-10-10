/**
 * Who made this. Set in frontend/.env.local (or the hosting dashboard) - never hard-coded, so personal details stay out of the repo.
 * NEXT_PUBLIC_* values are read at build time. Anything left empty is simply not shown.
 */
const clean = (v: string | undefined) => (v ?? "").trim();

export const CREDIT = {
  author: clean(process.env.NEXT_PUBLIC_AUTHOR),
  college: clean(process.env.NEXT_PUBLIC_COLLEGE),
  course: clean(process.env.NEXT_PUBLIC_COURSE),
  guide: clean(process.env.NEXT_PUBLIC_GUIDE),
} as const;

export const hasCredit = Boolean(CREDIT.author || CREDIT.college || CREDIT.course || CREDIT.guide);

/** One line, e.g. "Made by A · B College · Recommendation Systems". Empty when nothing is configured. */
export const creditLine = [CREDIT.author && `Made by ${CREDIT.author}`, CREDIT.college, CREDIT.course].filter(Boolean).join(" · ");

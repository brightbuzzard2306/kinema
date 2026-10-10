/**
 * WHO MADE THIS: the data behind the "Project → Team" tab.
 *
 * Right now everything below is PLACEHOLDER text. To fill it in, pick ONE way:
 *
 *  A) Edit `PLACEHOLDER_TEAM` / `PLACEHOLDER_INFO` below. Simple, but the names then live in the (public) GitHub repo.
 *  B) Keep names out of the repo: set these in frontend/.env.local (and in Vercel -> Settings -> Environment Variables):
 *       NEXT_PUBLIC_TEAM='[{"name":"Asha Rao","role":"Backend & evaluation","detail":"Roll no. 21CS001","links":[{"label":"GitHub","href":"https://github.com/..."}]}]'
 *       NEXT_PUBLIC_COLLEGE, NEXT_PUBLIC_COURSE, NEXT_PUBLIC_GUIDE   (plain text each)
 *     Environment values are read when the site is built, so redeploy after changing them. They are public by design.
 *
 * Photos are optional: put a square image in frontend/public/team/ and set `photo: "/team/asha.jpg"`. Without one, a monogram is shown.
 * Add or remove members freely: the layout adapts to any number.
 */
import { CREDIT } from "./credit";

export interface TeamLink {
  label: string;
  href: string;
}
export interface TeamMember {
  name: string;
  /** what they built / their responsibility */
  role: string;
  /** roll number, enrolment id, year... (optional) */
  detail?: string;
  /** e.g. "/team/asha.jpg" in frontend/public/team (optional) */
  photo?: string;
  links?: TeamLink[];
}
export interface ProjectInfo {
  college: string;
  course: string;
  guide: string;
  /** e.g. "Academic year 2026-27" (optional) */
  session?: string;
}

const PLACEHOLDER_TEAM: TeamMember[] = [
  { name: "Team member 1", role: "Role · what they built", detail: "Roll no. / ID" },
  { name: "Team member 2", role: "Role · what they built", detail: "Roll no. / ID" },
  { name: "Team member 3", role: "Role · what they built", detail: "Roll no. / ID" },
  { name: "Team member 4", role: "Role · what they built", detail: "Roll no. / ID" },
];

const PLACEHOLDER_INFO: ProjectInfo = {
  college: "Your college name",
  course: "Recommendation Systems · Mini Project",
  guide: "Guide's name",
  session: "Academic year 20XX-XX",
};

const text = (v: unknown, max = 120): string | undefined => (typeof v === "string" && v.trim() ? v.trim().slice(0, max) : undefined);

/** Accepts only well-formed members from the env JSON; anything odd is ignored instead of breaking the page. */
function parseTeam(raw: string | undefined): TeamMember[] | null {
  if (!raw?.trim()) return null;
  try {
    const data: unknown = JSON.parse(raw);
    if (!Array.isArray(data)) return null;
    const members = data.slice(0, 12).flatMap((m): TeamMember[] => {
      const name = text((m as TeamMember)?.name, 60);
      const role = text((m as TeamMember)?.role, 90);
      if (!name || !role) return [];
      const links = Array.isArray((m as TeamMember).links)
        ? ((m as TeamMember).links as TeamLink[])
            .filter((l) => text(l?.label, 24) && typeof l?.href === "string" && /^https?:\/\//i.test(l.href))
            .slice(0, 4)
            .map((l) => ({ label: l.label.trim().slice(0, 24), href: l.href.trim() }))
        : undefined;
      const photo = text((m as TeamMember).photo, 200);
      return [{ name, role, detail: text((m as TeamMember).detail, 60), photo: photo && /^(\/|https?:\/\/)/.test(photo) ? photo : undefined, links }];
    });
    return members.length ? members : null;
  } catch {
    return null;
  }
}

const fromEnv = parseTeam(process.env.NEXT_PUBLIC_TEAM);

export const TEAM: TeamMember[] = fromEnv ?? PLACEHOLDER_TEAM;
export const PROJECT_INFO: ProjectInfo = {
  college: CREDIT.college || PLACEHOLDER_INFO.college,
  course: CREDIT.course || PLACEHOLDER_INFO.course,
  guide: CREDIT.guide || PLACEHOLDER_INFO.guide,
  session: PLACEHOLDER_INFO.session,
};
/** True while any of the visible team text is still the placeholder (drives the dev-only "fill me in" hint). */
export const TEAM_IS_PLACEHOLDER = !fromEnv || !CREDIT.college || !CREDIT.guide;

export const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join("") || "?";

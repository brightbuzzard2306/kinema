/**
 * WHO MADE THIS: the data behind the "Project -> Team" tab (and the page footer).
 *
 * The defaults below are the real team, copied from the project cover page. To change them, pick ONE way:
 *
 *  A) Edit `DEFAULT_TEAM` / `DEFAULT_INFO` below. Simple, but the details then live in the (public) GitHub repo.
 *  B) Override from the environment (frontend/.env.local, and Vercel -> Settings -> Environment Variables):
 *       NEXT_PUBLIC_TEAM='[{"name":"Asha Rao","role":"Backend & evaluation","detail":"Roll no. 21CS001","links":[{"label":"GitHub","href":"https://github.com/..."}]}]'
 *       NEXT_PUBLIC_COLLEGE, NEXT_PUBLIC_COURSE, NEXT_PUBLIC_GUIDE   (plain text each)
 *     Environment values are read when the site is built, so redeploy after changing them.
 *
 * NOTE: the site's pages and scripts are served to anyone who opens the address (the access code protects the API, not these files),
 * so whatever is written here can be read by visitors. Only put in what you are happy to show publicly.
 *
 * Photos are optional: put a square image in frontend/public/team/ and set `photo: "/team/name.jpg"`. Without one, a monogram is shown.
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
  /** e.g. "Semester V · AI & Data Science" (optional) */
  session?: string;
  /** e.g. "/team/guide.jpg" in frontend/public/team (optional) */
  guidePhoto?: string;
}

const DEFAULT_TEAM: TeamMember[] = [
  { name: "Tisha Khatri", role: "AI & Data Science · Semester V", detail: "Roll no. S069 · SAP ID 60018250013" },
  { name: "Peher Sanghvi", role: "AI & Data Science · Semester V", detail: "Roll no. S067 · SAP ID 60018250010" },
  { name: "Moksh Mathukia", role: "AI & Data Science · Semester V", detail: "Roll no. S028 · SAP ID 60018240050" },
  { name: "Mantra Patel", role: "AI & Data Science · Semester V", detail: "Roll no. S035 · SAP ID 60018240086" },
];

const DEFAULT_INFO: ProjectInfo = {
  college: "Dwarkadas J. Sanghvi College of Engineering",
  course: "Natural Language Processing Laboratory (DJS23SPC302L)",
  guide: "Prof. Dashrath Kale",
  session: "Semester V · AI & Data Science",
  guidePhoto: "/team/guide.jpg",
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

export const TEAM: TeamMember[] = fromEnv ?? DEFAULT_TEAM;
export const PROJECT_INFO: ProjectInfo = {
  college: CREDIT.college || DEFAULT_INFO.college,
  course: CREDIT.course || DEFAULT_INFO.course,
  guide: CREDIT.guide || DEFAULT_INFO.guide,
  session: DEFAULT_INFO.session,
  // the bundled photo belongs to the default guide: don't show it next to a different name set through the environment
  guidePhoto: CREDIT.guide && CREDIT.guide !== DEFAULT_INFO.guide ? undefined : DEFAULT_INFO.guidePhoto,
};
/** True while any member still has the generic "Team member N" placeholder name (drives the dev-only "fill me in" hint). */
export const TEAM_IS_PLACEHOLDER = TEAM.some((m) => /^team member\b/i.test(m.name));

const joinNames = (names: string[]) => (names.length > 1 ? `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}` : (names[0] ?? ""));
/** One line for the page footer, e.g. "Made by A, B and C · Guide: Prof. X". */
export const teamCreditLine = TEAM_IS_PLACEHOLDER ? "" : `Made by ${joinNames(TEAM.map((m) => m.name))} · Guide: ${PROJECT_INFO.guide}`;

export const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join("") || "?";

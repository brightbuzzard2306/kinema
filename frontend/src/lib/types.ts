/** Types mirroring the FastAPI schemas in backend/app/schemas.py. */

export type Strategy = "hybrid" | "popular" | "content" | "collaborative";
export type Intent = "recommend" | "similar" | "explain" | "reject_last" | "reset" | "help" | "chitchat";
export type Confidence = "high" | "medium" | "low";
export type FeedbackAction = "like" | "dislike" | "clear";
export type ComponentName = "content" | "collaborative" | "popularity" | "preference";

export interface TasteProfile {
  liked_ids: number[];
  disliked_ids: number[];
  genres: string[];
  excluded_genres: string[];
  min_rating: number | null;
  year_min: number | null;
  year_max: number | null;
  novelty: number;
  strategy: Strategy;
  result_count: number;
}

export type ProfileUpdate = Partial<TasteProfile>;

export interface Reason {
  kind: "genre" | "content" | "collaborative" | "popularity" | "discovery" | string;
  text: string;
}

export interface MovieCardData {
  movie_id: number;
  title: string;
  year: number | null;
  genres: string[];
  mean_rating: number | null;
  n_ratings: number;
  score: number;
  components: Record<ComponentName, number | null>;
  weights_used: Partial<Record<ComponentName, number>>;
  reasons: Reason[];
  confidence: Confidence;
  confidence_basis: string;
  tmdb_id: number | null;
}

export interface MovieSummary {
  movie_id: number;
  title: string;
  year: number | null;
  genres: string[];
  mean_rating: number | null;
  n_ratings: number;
  tmdb_id: number | null;
}

export interface LLMStatus {
  mode: "claude" | "fallback";
  reason: string | null;
}

export interface ChatResponse {
  reply: string;
  intent: Intent;
  recommendations: MovieCardData[];
  notes: string[];
  suggestions: string[];
  profile: TasteProfile;
  strategy_used: string;
  llm: LLMStatus;
  unresolved_titles: string[];
  changes: string[];
}

export type CompareStrategy = "popular" | "content" | "collaborative" | "hybrid";

export interface CompareColumn {
  strategy_used: string;
  notes: string[];
  regime: "cold" | "thin" | "blend" | "warm" | null;
  movies: MovieCardData[];
}

export interface CompareResponse {
  columns: Record<CompareStrategy, CompareColumn>;
  signals: { liked: number; disliked: number; genres: string[]; excluded_genres: string[] };
  offline_ndcg: Record<CompareStrategy, number> | null;
}

export interface Health {
  status: "ok" | "unavailable";
  dataset: { ready: boolean; movies: number; ratings: number; users?: number; error: string | null };
  llm: { enabled: boolean; model: string | null };
  posters: { enabled: boolean };
  access?: { required: boolean };
}

export interface SpellCandidate {
  word: string;
  distance: number;
  channel: number;
  best_path_score: number;
  on_best_path: boolean;
}
export interface SpellToken {
  input: string;
  known: boolean;
  chosen: string;
  candidates: SpellCandidate[];
}
export interface SpellResult {
  query: string;
  tokens: SpellToken[];
  corrected: string;
  changed: boolean;
  matches: { movie_id: number; title: string; year: number | null }[];
}
export interface NlpReport {
  generated_at: string;
  corpus: { titles: number; title_tokens: number; extra_known_words: number };
  channel: { p_edit: number; max_edit_distance: number; bigram_k: number };
  perplexity: {
    n_train: number;
    n_valid: number;
    n_test: number;
    vocab: number;
    rows: { model: string; k: number; valid: number | null; test: number | null }[];
    chosen_k: number;
    test_at_chosen_k: number;
  };
  correction: {
    protocol: "seen" | "held-out";
    results: Record<"1_edit" | "2_edit", { items: number } & Record<string, { token_accuracy: number; title_accuracy: number } | number>>;
    false_correction_rate?: Record<string, number>;
  }[];
}

export interface LlmCheck {
  enabled: boolean;
  ok: boolean;
  reason: string | null;
  model: string | null;
}

export interface Meta {
  genres: string[];
  strategies: Strategy[];
  max_results: number;
  max_message_chars: number;
}

export interface SessionState {
  profile: TasteProfile;
  last_cards: MovieCardData[];
  history: { role: "user" | "assistant"; text: string }[];
}

export interface MetricRow {
  precision: number;
  recall: number;
  ndcg: number;
  hit_rate: number;
  catalogue_coverage: number;
  ndcg_std: number;
}

export interface EvaluationReport {
  generated_at: string;
  dataset: string;
  protocol: Record<string, string | number>;
  chosen_config: { knn: Record<string, string | number>; hybrid_weights: Record<string, number> | null };
  metrics: Record<"random" | "popular" | "content" | "collaborative" | "hybrid", MetricRow>;
  paired_comparisons?: Record<
    string,
    { mean_ndcg_difference: number; ci95_low: number; ci95_high: number; significant_at_95: boolean }
  >;
  n_users_evaluated: number;
  n_test_interactions: number;
  n_relevant_test_interactions: number;
  n_train_interactions: number;
  n_candidate_items: number;
  runtime_seconds?: number;
}

/** A message in the conversation view. */
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  cards?: MovieCardData[];
  notes?: string[];
  changes?: string[];
  suggestions?: string[];
  unresolved?: string[];
  llm?: LLMStatus;
  /** user message that failed to send; shown with a retry button */
  failed?: boolean;
  pending?: boolean;
  intent?: Intent;
}

/** Progress events from the streaming endpoints (real milestones of the turn). */
export interface StepEvent {
  step: "interpret" | "rank" | "write";
  strategy?: Strategy;
}
export interface CardsEvent {
  intent: Intent;
  cards: MovieCardData[];
  notes: string[];
  changes: string[];
  unresolved: string[];
  strategy_used: string;
  profile: TasteProfile;
}
export interface StreamHandlers {
  onStep?: (e: StepEvent) => void;
  onCards?: (e: CardsEvent) => void;
}

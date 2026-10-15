export type Cell = string | number | boolean | null;
export type Mode = "natural_language" | "sql";
export interface Confidence {
  syntax_valid: number;
  back_translation_alignment: number;
  result_sanity: number;
  schema_coverage: number;
  overall: number;
  multi_query_agreement: number | null;
}
export interface QueryResult {
  query_id: string;
  question: string;
  sql: string | null;
  explanation: string | null;
  columns: string[];
  rows: Cell[][];
  row_count: number;
  total_rows_available: number;
  execution_time_ms: number | null;
  confidence: Confidence | null;
  status: "success" | "blocked" | "error" | "clarification_needed";
  error_message: string | null;
  tables_used: string[];
  hallucination_flags: string[];
  guardrail_violations: { rule: string; detail: string; severity: string }[];
  clarification_options: {
    label: string;
    description: string;
    example_sql: string;
  }[];
}
export interface HistoryItem {
  query_id: string;
  question: string;
  sql: string | null;
  status: string;
  confidence: number | null;
  is_correct: boolean | null;
  timestamp: string;
}
export interface AppConfig {
  provider: string;
  ai_configured: boolean;
  live_evals_enabled: boolean;
  eval_cases: number;
  max_rows: number;
}
export interface EvalResult {
  shape_pass_rate: number;
  guardrail_effectiveness: number;
  flagged_case_rate: number;
  average_confidence: number;
  details: { question: string; passed: boolean; notes?: string[] }[];
}
export interface Schema {
  tables: {
    name: string;
    comment: string | null;
    primary_keys: string[];
    columns: { name: string; type: string }[];
    foreign_keys: {
      column: string;
      references_table: string;
      references_column: string;
    }[];
  }[];
}

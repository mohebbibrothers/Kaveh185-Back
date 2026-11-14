/**
 * Kaveh185 Official Frontend TypeScript SDK & Contract Types (v1)
 * سامانه مسابقه بزرگ فرهنگی و کتابخوانی هفته بسیج — حوزه مقاومت بسیج ۱۸۵ شهید کاوه
 *
 * نحوه استفاده در Next.js / React / Vue:
 *   import { Kaveh185ApiClient } from "./kaveh185-frontend-sdk";
 *   const api = new Kaveh185ApiClient({ baseUrl: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000" });
 */

export interface ApiSuccessEnvelope<T> {
  success: true;
  status_code: number;
  code: string;
  message: string;
  trace_id: string;
  data: T;
}

export interface ApiErrorEnvelope {
  success: false;
  status_code: number;
  code: string;
  message: string;
  trace_id: string;
  errors?: Record<string, unknown>;
}

export type WindowState = "upcoming" | "open" | "ended";

export interface CommunicationChannel {
  platform: "eitaa" | "bale" | "rubika" | "telegram" | "soroush" | string;
  title: string;
  url: string;
  handle?: string;
}

export interface PublicExamStatus {
  title: string;
  book_title: string;
  organizer_name: string;
  description: string;
  window_state: WindowState;
  window_state_label: string;
  can_participate: boolean;
  status_message: string;
  server_time: string;
  server_time_jalali: string;
  starts_at: string;
  starts_at_jalali: string;
  ends_at: string;
  ends_at_jalali: string;
  seconds_until_start: number;
  seconds_until_end: number;
  duration_seconds: number;
  questions_per_attempt: number;
  require_otp_before_exam: boolean;
  active_question_bank_size: number;
  communication_channels: CommunicationChannel[];
}

export interface MosqueDropdownItem {
  id: number;
  code: string;
  name: string;
  neighborhood: string;
  address?: string;
}

export interface MosqueLeaderboardEntry {
  rank: number;
  id: number;
  mosque_id: number;
  code: string;
  name: string;
  neighborhood: string;
  registered_users_count: number;
  participants_count: number;
  completed_exams_count: number;
  participation_share_percent: number;
}

export interface MosqueLeaderboardSnapshot {
  total_active_mosques: number;
  total_registered_participants: number;
  total_exam_participants: number;
  updated_at: string;
  updated_at_jalali: string;
  leaderboard: MosqueLeaderboardEntry[];
}

export interface PublicLandingBootstrap {
  server_time: string;
  server_time_jalali: string;
  exam_status: PublicExamStatus;
  mosques: MosqueDropdownItem[];
  leaderboard: MosqueLeaderboardSnapshot;
}

export interface RegisterParticipantInput {
  first_name: string;
  last_name: string;
  national_id: string;
  phone_number: string;
  /** تاریخ تولد شمسی (مثلاً "1382/06/15" یا "۱۳۸۲/۰۶/۱۵") یا میلادی ("2003-09-06") */
  birth_date: string;
  mosque_id: number;
}

export interface AuthTokens {
  access: string;
  refresh: string;
  session_uid: string;
}

export interface UserProfile {
  id: number;
  first_name: string;
  last_name: string;
  full_name: string;
  phone_number: string;
  national_id: string;
  birth_date: string | null;
  birth_date_jalali: string | null;
  age_years: number | null;
  mosque_id: number | null;
  mosque_name: string | null;
  role: "participant" | "operator" | "admin";
  is_phone_verified: boolean;
}

export interface RegisterParticipantOutput {
  is_new_user: boolean;
  otp_required: boolean;
  access?: string;
  refresh?: string;
  session_uid?: string;
  tokens?: AuthTokens | null;
  user: UserProfile;
  exam_eligibility: {
    can_enter_exam: boolean;
    has_completed_exam: boolean;
    has_active_attempt: boolean;
    tracking_code: string | null;
    reason_code: string;
    message: string;
  };
}

export interface ExamQuestionSafeOption {
  position: 1 | 2 | 3 | 4;
  text: string;
}

export interface ExamQuestionSafeItem {
  question_number: number;
  question_text: string;
  chapter: string;
  selected_position: 1 | 2 | 3 | 4 | null;
  is_answered: boolean;
  options: ExamQuestionSafeOption[];
}

export interface ActiveExamAttempt {
  attempt_id: number;
  tracking_code: string;
  status: "in_progress" | "completed" | "timed_out";
  started_at: string;
  started_at_jalali: string;
  expires_at: string;
  duration_limit_seconds: number;
  remaining_seconds: number;
  total_questions: number;
  answered_count: number;
  unanswered_count: number;
  current_question_number: number | null;
  can_finish_now: boolean;
  questions: ExamQuestionSafeItem[];
}

export interface ExamReportCard {
  tracking_code: string;
  receipt_signature: string;
  participant: {
    id: number;
    full_name: string;
    national_id_masked: string;
    phone_masked: string;
    age_years: number | null;
    mosque_id: number;
    mosque_name: string;
  };
  summary: {
    status: "completed" | "timed_out";
    status_label: string;
    finished_reason: "completed_by_user" | "time_expired";
    started_at: string;
    started_at_jalali: string;
    completed_at: string;
    completed_at_jalali: string;
    total_questions: number;
    correct_count: number;
    wrong_count: number;
    unanswered_count: number;
    accuracy_percent: number;
    duration_seconds: number;
    duration_display: string;
    base_score: number;
    time_bonus_score: number;
    total_score: number;
  };
  thank_you_message: string;
  communication_channels: CommunicationChannel[];
}

export interface AdminLotteryFilterParams {
  mosque_ids?: string;
  mosque_id?: number;
  exact_correct?: number;
  min_correct?: number;
  max_correct?: number;
  min_wrong?: number;
  max_wrong?: number;
  min_unanswered?: number;
  max_unanswered?: number;
  min_score?: number;
  max_score?: number;
  min_duration?: number;
  max_duration?: number;
  min_age?: number;
  max_age?: number;
  birth_date_from?: string;
  birth_date_to?: string;
  status?: "finished" | "completed" | "timed_out" | "in_progress";
  search?: string;
  ordering?: string;
  include_answers?: boolean;
  limit?: number;
  offset?: number;
}

export interface AdminLotteryDrawInput extends AdminLotteryFilterParams {
  winners_count?: number;
  reserves_count?: number;
  ceremony_title?: string;
  client_seed?: string;
}

export interface Kaveh185ClientOptions {
  baseUrl: string;
  getAccessToken?: () => string | null;
}

export class Kaveh185ApiClient {
  private readonly baseUrl: string;
  private readonly getAccessToken?: () => string | null;

  constructor(options: Kaveh185ClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, "");
    this.getAccessToken = options.getAccessToken;
  }

  private async request<T>(
    path: string,
    init: RequestInit = {},
    idempotencyKey?: string,
  ): Promise<ApiSuccessEnvelope<T>> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(init.headers as Record<string, string> | undefined),
    };
    const token = this.getAccessToken?.();
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    if (idempotencyKey) {
      headers["Idempotency-Key"] = idempotencyKey;
    }

    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers,
      credentials: "include",
    });

    const payload = await response.json();
    if (!response.ok || !payload.success) {
      throw payload as ApiErrorEnvelope;
    }
    return payload as ApiSuccessEnvelope<T>;
  }

  /** ۱. دریافت یکپارچه تمام داده‌های صفحه اول (وضعیت آزمون + ۱۷ مسجد + رنکینگ مساجد) */
  getLandingBootstrap() {
    return this.request<PublicLandingBootstrap>("/api/v1/core/bootstrap/");
  }

  /** ۲. وضعیت بازه زمانی آزمون */
  getExamStatus() {
    return this.request<PublicExamStatus>("/api/v1/exam/status/");
  }

  /** ۳. لیست کشویی ۱۷ مسجد فعال برای فرم ثبت‌نام */
  getMosquesDropdown() {
    return this.request<MosqueDropdownItem[]>("/api/v1/mosques/");
  }

  /** ۴. جدول رنکینگ زنده مشارکت مساجد */
  getMosquesLeaderboard() {
    return this.request<MosqueLeaderboardSnapshot>("/api/v1/mosques/leaderboard/");
  }

  /** ۵. ثبت‌نام شرکت‌کننده و دریافت توکن ورود مستقیم به آزمون */
  registerParticipant(body: RegisterParticipantInput, idempotencyKey?: string) {
    return this.request<RegisterParticipantOutput>(
      "/api/v1/auth/register/",
      { method: "POST", body: JSON.stringify(body) },
      idempotencyKey,
    );
  }

  /** ۶. کلیک روی دکمه «ورود به آزمون» (شروع تایمر ۵ سواله یا ادامه آزمون باز) */
  startExam(idempotencyKey?: string) {
    return this.request<ActiveExamAttempt>(
      "/api/v1/exam/start/",
      { method: "POST", body: JSON.stringify({}) },
      idempotencyKey,
    );
  }

  /** ۷. بازیابی جلسه فعال آزمون (هنگام رفرش صفحه توسط کاربر) */
  getCurrentExam() {
    return this.request<ActiveExamAttempt | { exam_finished: true; report_card: ExamReportCard }>(
      "/api/v1/exam/current/",
    );
  }

  /** ۸. ثبت پاسخ هر سوال به ترتیب ۱ تا ۵ (بدون امکان رد کردن سوال قبلی) */
  submitAnswer(questionNumber: number, selectedPosition: 1 | 2 | 3 | 4) {
    return this.request<ActiveExamAttempt>("/api/v1/exam/answer/", {
      method: "POST",
      body: JSON.stringify({
        question_number: questionNumber,
        selected_position: selectedPosition,
      }),
    });
  }

  /** ۹. پایان آزمون و دریافت کارنامه نهایی */
  finishExam(idempotencyKey?: string) {
    return this.request<ExamReportCard>(
      "/api/v1/exam/finish/",
      { method: "POST", body: JSON.stringify({}) },
      idempotencyKey,
    );
  }

  /** ۱۰. مشاهده مجدد کارنامه شرکت‌کننده */
  getReportCard() {
    return this.request<ExamReportCard>("/api/v1/exam/report-card/");
  }

  /** ۱۱. اجرای قرعه‌کشی زنده در پنل ادمین با گواهی اثبات رمزنگاری‌شده */
  drawLiveLottery(input: AdminLotteryDrawInput) {
    return this.request< Record<string, unknown> >("/api/v1/reporting/admin/lottery/draw/", {
      method: "POST",
      body: JSON.stringify(input),
    });
  }
}

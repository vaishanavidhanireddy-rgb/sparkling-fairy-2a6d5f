import { sql } from "drizzle-orm";
import {
  boolean,
  doublePrecision,
  index,
  integer,
  pgTable,
  serial,
  text,
  timestamp,
  uniqueIndex,
} from "drizzle-orm/pg-core";

// Timestamps are stored as "YYYY-MM-DD HH:MM:SS" text (UTC), matching the format
// the React UI and the date-range filters already expect from the old SQLite app.
const createdAt = () =>
  text("created_at")
    .notNull()
    .default(sql`to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')`);

export const users = pgTable(
  "users",
  {
    id: serial().primaryKey(),
    email: text().notNull(),
    passwordHash: text("password_hash").notNull(),
    phone: text(),
    firebaseUid: text("firebase_uid"),
    state: text(),
    area: text(),
    country: text().notNull().default("India"),
    createdAt: createdAt(),
  },
  (t) => [uniqueIndex("users_email_unique").on(t.email), uniqueIndex("users_firebase_uid").on(t.firebaseUid)],
);

export const sessions = pgTable(
  "sessions",
  {
    id: text().primaryKey(),
    userId: integer("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    email: text().notNull(),
    profileRequired: boolean("profile_required").notNull().default(false),
    expiresAt: timestamp("expires_at", { withTimezone: true }).notNull(),
  },
  (t) => [index("sessions_by_user").on(t.userId)],
);

export const reports = pgTable(
  "reports",
  {
    id: serial().primaryKey(),
    userId: integer("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    title: text().notNull(),
    content: text().notNull(),
    explanation: text().notNull().default(""),
    // Key of the original uploaded file in the "report-files" Netlify Blobs store.
    fileKey: text("file_key").notNull().default(""),
    mimeType: text("mime_type").notNull().default(""),
    createdAt: createdAt(),
  },
  (t) => [index("reports_by_user").on(t.userId, t.createdAt)],
);

export const medications = pgTable("medications", {
  id: serial().primaryKey(),
  userId: integer("user_id")
    .notNull()
    .references(() => users.id, { onDelete: "cascade" }),
  name: text().notNull(),
  instructions: text().notNull().default(""),
  reminderTime: text("reminder_time").notNull(),
  active: boolean().notNull().default(true),
  createdAt: createdAt(),
});

export const wellnessLogs = pgTable(
  "wellness_logs",
  {
    id: serial().primaryKey(),
    userId: integer("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    logDate: text("log_date").notNull(),
    waterGlasses: integer("water_glasses").notNull().default(0),
    sleepHours: doublePrecision("sleep_hours").notNull().default(0),
    exerciseMinutes: integer("exercise_minutes").notNull().default(0),
    steps: integer().notNull().default(0),
    focus: text().notNull().default(""),
    createdAt: createdAt(),
  },
  (t) => [uniqueIndex("wellness_logs_user_date").on(t.userId, t.logDate)],
);

export const appointmentHospitals = pgTable(
  "appointment_hospitals",
  {
    id: serial().primaryKey(),
    hospitalName: text("hospital_name").notNull(),
    state: text().notNull(),
    district: text().notNull(),
    city: text().notNull(),
    area: text().notNull(),
    address: text().notNull().default(""),
    phone: text().notNull().default(""),
    category: text().notNull().default(""),
    careType: text("care_type").notNull().default(""),
    specialties: text().notNull().default(""),
    pincode: text().notNull().default(""),
    coordinates: text().notNull().default(""),
    sourceType: text("source_type").notNull().default("admin_uploaded"),
    sourceRecordId: text("source_record_id").notNull().default(""),
    sourceUrl: text("source_url").notNull().default(""),
    importedAt: text("imported_at").notNull().default(sql`to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')`),
    createdAt: createdAt(),
  },
  (t) => [
    uniqueIndex("appointment_hospitals_unique").on(
      sql`lower(${t.hospitalName})`,
      sql`lower(${t.state})`,
      sql`lower(${t.district})`,
      sql`lower(${t.city})`,
      sql`lower(${t.area})`,
    ),
    index("appointment_hospitals_location").on(sql`lower(${t.state})`, sql`lower(${t.district})`, sql`lower(${t.city})`),
  ],
);

export const appointmentStates = pgTable(
  "appointment_states",
  {
    id: serial().primaryKey(),
    state: text().notNull(),
    sourceCode: text("source_code").notNull().default(""),
    sourceUrl: text("source_url").notNull(),
    active: boolean().notNull().default(true),
    importedAt: text("imported_at").notNull().default(sql`to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')`),
  },
  (t) => [uniqueIndex("appointment_states_unique").on(sql`lower(${t.state})`)],
);

export const appointmentDistricts = pgTable(
  "appointment_districts",
  {
    id: serial().primaryKey(),
    state: text().notNull(),
    district: text().notNull(),
    sourceCode: text("source_code").notNull().default(""),
    sourceUrl: text("source_url").notNull(),
    active: boolean().notNull().default(true),
    importedAt: text("imported_at").notNull().default(sql`to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')`),
  },
  (t) => [uniqueIndex("appointment_districts_unique").on(sql`lower(${t.state})`, sql`lower(${t.district})`)],
);

export const appointmentLocations = pgTable(
  "appointment_locations",
  {
    id: serial().primaryKey(),
    state: text().notNull(),
    district: text().notNull(),
    city: text().notNull(),
    sourceCode: text("source_code").notNull().default(""),
    pincodes: text().notNull().default(""),
    sourceUrl: text("source_url").notNull(),
    active: boolean().notNull().default(true),
    importedAt: text("imported_at").notNull().default(sql`to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')`),
  },
  (t) => [
    uniqueIndex("appointment_locations_unique").on(sql`lower(${t.state})`, sql`lower(${t.district})`, sql`lower(${t.city})`),
  ],
);

export const appointmentDoctors = pgTable(
  "appointment_doctors",
  {
    id: serial().primaryKey(),
    hospitalId: integer("hospital_id")
      .notNull()
      .references(() => appointmentHospitals.id, { onDelete: "cascade" }),
    doctorName: text("doctor_name").notNull(),
    specialty: text().notNull().default(""),
    registrationNumber: text("registration_number").notNull().default(""),
    verificationUrl: text("verification_url").notNull().default(""),
    verificationStatus: text("verification_status").notNull().default("unverified"),
    sourceType: text("source_type").notNull().default("admin_uploaded"),
    createdAt: createdAt(),
  },
  (t) => [
    uniqueIndex("appointment_doctors_unique").on(t.hospitalId, sql`lower(${t.doctorName})`, t.registrationNumber),
  ],
);

export const appointmentRequests = pgTable(
  "appointment_requests",
  {
    id: serial().primaryKey(),
    userId: integer("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    hospitalId: integer("hospital_id")
      .notNull()
      .references(() => appointmentHospitals.id, { onDelete: "cascade" }),
    doctorId: integer("doctor_id").references(() => appointmentDoctors.id, { onDelete: "set null" }),
    appointmentDate: text("appointment_date").notNull().default(""),
    timeSlot: text("time_slot").notNull().default("any"),
    bookingKey: text("booking_key"),
    bookingMode: text("booking_mode").notNull().default("demo_request"),
    appointmentAt: text("appointment_at").notNull(),
    reason: text().notNull().default(""),
    status: text().notNull().default("pending"),
    createdAt: createdAt(),
  },
  (t) => [
    index("appointments_by_user").on(t.userId, t.appointmentAt),
    uniqueIndex("appointment_request_dedupe").on(t.bookingKey),
  ],
);

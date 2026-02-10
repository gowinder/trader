CREATE TABLE "advisories" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"trigger_type" varchar(30) NOT NULL,
	"trigger_detail" jsonb,
	"urgency" varchar(10) NOT NULL,
	"market_summary" text,
	"status" varchar(20) DEFAULT 'pending' NOT NULL,
	"llm_provider" varchar(30),
	"llm_model" varchar(100),
	"tokens_used" integer,
	"resolved_at" timestamp with time zone
);
--> statement-breakpoint
CREATE TABLE "advisory_suggestions" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"advisory_id" uuid NOT NULL,
	"sort_order" integer DEFAULT 0 NOT NULL,
	"type" varchar(20) NOT NULL,
	"target" varchar(30) NOT NULL,
	"action" varchar(50) NOT NULL,
	"detail" jsonb,
	"reasoning" text,
	"risk_note" text,
	"status" varchar(20) DEFAULT 'pending' NOT NULL,
	"execution_result" jsonb,
	"rejection_reason" text,
	"updated_at" timestamp with time zone
);
--> statement-breakpoint
ALTER TABLE "advisory_suggestions" ADD CONSTRAINT "advisory_suggestions_advisory_id_advisories_id_fk" FOREIGN KEY ("advisory_id") REFERENCES "public"."advisories"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "idx_advisories_time" ON "advisories" USING btree ("created_at");--> statement-breakpoint
CREATE INDEX "idx_advisories_status" ON "advisories" USING btree ("status");--> statement-breakpoint
CREATE INDEX "idx_advisory_suggestions_advisory" ON "advisory_suggestions" USING btree ("advisory_id");--> statement-breakpoint
CREATE INDEX "idx_advisory_suggestions_status" ON "advisory_suggestions" USING btree ("status");
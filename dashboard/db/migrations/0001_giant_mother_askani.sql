CREATE TABLE "llm_usage" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"provider" varchar(30) NOT NULL,
	"model" varchar(100) NOT NULL,
	"input_tokens" integer DEFAULT 0,
	"output_tokens" integer DEFAULT 0,
	"total_tokens" integer DEFAULT 0,
	"cost_usd" numeric(12, 8) DEFAULT '0',
	"latency_ms" integer DEFAULT 0,
	"success" boolean DEFAULT true,
	"error_message" text,
	"decision_id" uuid
);
--> statement-breakpoint
ALTER TABLE "llm_usage" ADD CONSTRAINT "llm_usage_decision_id_decisions_id_fk" FOREIGN KEY ("decision_id") REFERENCES "public"."decisions"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "idx_llm_usage_time" ON "llm_usage" USING btree ("created_at");--> statement-breakpoint
CREATE INDEX "idx_llm_usage_provider" ON "llm_usage" USING btree ("provider");
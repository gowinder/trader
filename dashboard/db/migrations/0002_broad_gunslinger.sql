CREATE TABLE "active_strategy" (
	"id" integer PRIMARY KEY GENERATED ALWAYS AS IDENTITY (sequence name "active_strategy_id_seq" INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START WITH 1 CACHE 1),
	"preset_id" integer NOT NULL,
	"activated_at" timestamp with time zone DEFAULT now() NOT NULL,
	"deactivated_at" timestamp with time zone
);
--> statement-breakpoint
CREATE TABLE "strategy_presets" (
	"id" integer PRIMARY KEY GENERATED ALWAYS AS IDENTITY (sequence name "strategy_presets_id_seq" INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START WITH 1 CACHE 1),
	"name" varchar(50) NOT NULL,
	"display_name" varchar(100) NOT NULL,
	"description" text,
	"category" varchar(20) NOT NULL,
	"risk_level" varchar(20) NOT NULL,
	"config_json" jsonb NOT NULL,
	"is_system" boolean DEFAULT true NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "strategy_presets_name_unique" UNIQUE("name")
);
--> statement-breakpoint
ALTER TABLE "active_strategy" ADD CONSTRAINT "active_strategy_preset_id_strategy_presets_id_fk" FOREIGN KEY ("preset_id") REFERENCES "public"."strategy_presets"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "idx_active_strategy_active" ON "active_strategy" USING btree ("deactivated_at");--> statement-breakpoint
CREATE UNIQUE INDEX "idx_strategy_presets_name" ON "strategy_presets" USING btree ("name");
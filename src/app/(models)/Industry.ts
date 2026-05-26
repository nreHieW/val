import mongoose, { Schema, Document } from "mongoose";

export interface IIndustry extends Document {
  industry_key: string;
  sector_key?: string;
  sector_name?: string;
  industry_name?: string;
  symbol?: string;
  market_weight?: number;
  overview?: Record<string, unknown>;
  top_companies?: Record<string, unknown>[];
  performance_pct?: Record<string, number | null>;
  [key: string]: unknown;
}

const industrySchema: Schema = new Schema(
  {
    industry_key: {
      type: String,
      required: true,
    },
  },
  {
    strict: false,
  },
);

industrySchema.index({ industry_key: 1 });
industrySchema.index({ sector_key: 1 });

const Industry =
  mongoose.models.industries ||
  mongoose.model<IIndustry>("industries", industrySchema);

export default Industry;

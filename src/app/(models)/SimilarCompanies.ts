import mongoose, { Schema, Document } from "mongoose";

export interface ISimilarCompanies extends Document {
  Ticker: string;
  similar_tickers?: string[];
  similar_companies?: Record<string, unknown>[];
  [key: string]: unknown;
}

const similarCompaniesSchema: Schema = new Schema(
  {
    Ticker: {
      type: String,
      required: true,
    },
    similar_tickers: {
      type: [String],
      default: [],
    },
    similar_companies: {
      type: [Schema.Types.Mixed],
      default: [],
    },
  },
  {
    strict: false,
  },
);

similarCompaniesSchema.index({ Ticker: 1 });

const SimilarCompanies =
  mongoose.models.similar_companies ||
  mongoose.model<ISimilarCompanies>("similar_companies", similarCompaniesSchema);

export default SimilarCompanies;

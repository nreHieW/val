import mongoose, { Schema, Document } from "mongoose";

export interface IFinancials extends Document {
  [key: string]: unknown;
}

const financialsSchema: Schema = new Schema(
  {
    Ticker: {
      type: String,
    },
    Name: {
      type: String,
    },
  },
  {
    strict: false,
  }
);

financialsSchema.index({ Ticker: 1 });
financialsSchema.index({ Name: 1 });

const Financials =
  mongoose.models.financials ||
  mongoose.model<IFinancials>("financials", financialsSchema);

export default Financials;

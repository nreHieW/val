import mongoose, { Schema, Document } from "mongoose";

export interface ITickerOverview extends Document {
  Ticker: string;
  [key: string]: unknown;
}

const tickerOverviewSchema: Schema = new Schema(
  {
    Ticker: {
      type: String,
      required: true,
    },
  },
  {
    strict: false,
  },
);

tickerOverviewSchema.index({ Ticker: 1 });

const TickerOverview =
  mongoose.models.ticker_overviews ||
  mongoose.model<ITickerOverview>("ticker_overviews", tickerOverviewSchema);

export default TickerOverview;

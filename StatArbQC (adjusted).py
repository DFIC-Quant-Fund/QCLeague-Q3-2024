# region imports
from AlgorithmImports import *
# endregion

class wrapper(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(2023, 12, 10)
        self.SetEndDate(2024, 9, 10)
        self.SetCash(100000)

        # Create instances of the SymbolData class for different stock pairs
        self.model = [
            meanReversion(self, "DIS", "MRK"),
            meanReversion(self, "AMZN", "MPC"),
        ]

    def OnData(self, data):
        for model in self.model:
            model.bb.Update(self.Time, model.series.Current.Value)
            model.OnData(data)


class meanReversion:

    def __init__(self, algorithm, tickr1, tickr2):
        self.algorithm = algorithm

        self.ticker_1 = algorithm.AddEquity(tickr1, Resolution.Daily).Symbol
        self.ticker_2 = algorithm.AddEquity(tickr2, Resolution.Daily).Symbol

        # Create two identity indicators (a indicator that repeats the value without any processing)
        self.ticker_1_identity = Identity(tickr1)
        self.ticker_2_identity = Identity(tickr2)

        # Set these indicators to receive the data from ticker_1 and ticker_2
        algorithm.RegisterIndicator(
            self.ticker_1, self.ticker_1_identity, Resolution.Daily)
        algorithm.RegisterIndicator(
            self.ticker_2, self.ticker_2_identity, Resolution.Daily)

        # Create the portfolio as a new indicator using slope of linear regression in research.ipynb
        self.series = IndicatorExtensions.Minus(
            self.ticker_1_identity, IndicatorExtensions.Times(self.ticker_2_identity, 0.356))

        # Bollinger Bands with 120-step lookback period
        self.bb = BollingerBands(120, 0.6, MovingAverageType.Exponential)

        # Track volatility for dynamic position sizing
        self.volatility_1 = StandardDeviation(120)
        self.volatility_2 = StandardDeviation(120)

        algorithm.RegisterIndicator(self.ticker_1, self.volatility_1, Resolution.Daily)
        algorithm.RegisterIndicator(self.ticker_2, self.volatility_2, Resolution.Daily)

        self.is_invested = None

    def OnData(self, data):
        # For daily bars data is delivered at 00:00 of the day containing the closing price of the previous day (23:59:59)
        if (not data.Bars.ContainsKey(self.ticker_1)) or (not data.Bars.ContainsKey(self.ticker_2)):
            return

        # Check if the bolllinger band indicator is ready (filled with 120 steps)
        if not self.bb.IsReady or not self.volatility_1.IsReady or not self.volatility_2.IsReady:
            return

        serie = self.series.Current.Value

        # Calculate volatility-adjusted position size
        vol_1 = self.volatility_1.Current.Value
        vol_2 = self.volatility_2.Current.Value

        total_volatility = vol_1 + vol_2
        weight_1 = vol_2 / total_volatility  # inverse proportion of volatility
        weight_2 = vol_1 / total_volatility

        # Adjust portfolio targets based on volatility
        long_targets = [PortfolioTarget(self.ticker_1, weight_1),
                        PortfolioTarget(self.ticker_2, -weight_2)]
        short_targets = [PortfolioTarget(self.ticker_1, -weight_1),
                         PortfolioTarget(self.ticker_2, weight_2)]

        # Plot relevant indicators
        self.algorithm.Plot("ticker_2 Prices", "Open",
                            self.algorithm.Securities[self.ticker_2].Open)
        self.algorithm.Plot("ticker_2 Prices", "Close",
                            self.algorithm.Securities[self.ticker_2].Close)

        self.algorithm.Plot("Indicators", "Serie", serie)
        self.algorithm.Plot("Indicators", "Middle",
                            self.bb.MiddleBand.Current.Value)  # moving average
        self.algorithm.Plot("Indicators", "Upper",
                            self.bb.UpperBand.Current.Value)   # upper band
        self.algorithm.Plot("Indicators", "Lower",
                            self.bb.LowerBand.Current.Value)   # lower band

        # If not invested, check entry point
        if not self.is_invested:
            # If portfolio is below the lower band, enter long
            if serie < self.bb.LowerBand.Current.Value:
                self.algorithm.SetHoldings(long_targets)
                self.algorithm.Debug('Entering Long with adjusted weights')
                self.is_invested = 'long'

            # If portfolio is above the upper band, go short
            if serie > self.bb.UpperBand.Current.Value:
                self.algorithm.SetHoldings(short_targets)
                self.algorithm.Debug('Entering Short with adjusted weights')
                self.is_invested = 'short'

        # If invested, check for exit signal (when it crosses the mean)
        elif self.is_invested == 'long':
            if serie > self.bb.MiddleBand.Current.Value:
                self.algorithm.Liquidate()
                self.algorithm.Debug('Exiting Long')
                self.is_invested = None

        elif self.is_invested == 'short':
            if serie < self.bb.MiddleBand.Current.Value:
                self.algorithm.Liquidate()
                self.algorithm.Debug('Exiting Short')
                self.is_invested = None

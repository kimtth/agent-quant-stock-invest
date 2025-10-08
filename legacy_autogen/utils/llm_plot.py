import seaborn as sns
import pandas as pd
import os
import matplotlib.pyplot as plt
import random
from utils.const import WORK_DIR, BACKTEST_RESULTS_FILE, PLOT_FILE_NAME


def plot_backtest_results():
    """
    Plot backtest results from an Excel file and save the plot as a PNG file.
    """
    abs_path = os.path.abspath(WORK_DIR)
    file_path = os.path.join(abs_path, BACKTEST_RESULTS_FILE)

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    plot_output_path = os.path.join(abs_path, PLOT_FILE_NAME)

    # Load the data
    df = pd.read_excel(file_path)

    # Convert date column to datetime if necessary
    df["Date"] = pd.to_datetime(df["Date"])

    # Set Date as index
    df.set_index("Date", inplace=True)

    # Resample to get the last trading day of each month and year
    monthly_data = df.resample("ME").last()
    # yearly_data = df.resample('Y').last()

    # Define colors
    colors = ["red", "orange"]
    mdd_color = random.choice(colors)

    # Create subplots
    fig, axs = plt.subplots(2, 1, figsize=(10, 8))

    # Plot Cumulative Returns
    axs[0].plot(
        monthly_data.index,
        monthly_data["Cumulative Returns"],
        label="Cumulative Returns",
        color="blue",
    )
    axs[0].set_title("Cumulative Returns Over Time")
    axs[0].set_ylabel("Cumulative Returns")
    axs[0].legend()

    # Plot MDD with random color
    axs[1].plot(monthly_data.index, monthly_data["MDD"], label="MDD", color=mdd_color)
    axs[1].set_title("Maximum Drawdown Over Time")
    axs[1].set_ylabel("MDD (%)")
    axs[1].legend()

    # Save the plot
    plt.tight_layout()
    plt.savefig(plot_output_path)
    plt.close()



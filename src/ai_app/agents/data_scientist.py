from .base import BaseSpecialistAgent

_SYSTEM = """You are a senior data scientist specializing in statistical analysis, experimentation, and ML-driven insights.

Your responsibilities:
- Exploratory data analysis (EDA) with pandas, matplotlib, seaborn, plotly
- Statistical hypothesis testing (t-tests, chi-square, ANOVA, Mann-Whitney)
- A/B testing design and analysis (sample size, power, MDE, multiple testing corrections)
- Causal inference (DiD, synthetic control, propensity score matching)
- Feature importance and interpretability (SHAP, LIME, partial dependence plots)
- Time series forecasting (Prophet, ARIMA, statsmodels)
- Clustering and dimensionality reduction (K-means, DBSCAN, UMAP, t-SNE)
- Write analysis reports with clear findings and business recommendations
- Build Jupyter notebooks with reproducible, documented analyses
- Bayesian inference (PyMC, Stan)

When writing code:
- Always include descriptive statistics and distributions first
- Verify assumptions before applying statistical tests
- Report effect sizes alongside p-values
- Use visualizations to communicate findings
- Document what the numbers mean in business terms
- Write reproducible code: set seeds, pin library versions in comments
- Separate data prep, analysis, and visualization into clear sections

Always produce rigorous, well-documented data science code."""


class DataScientistAgent(BaseSpecialistAgent):
    name = "data_scientist"
    role = "Data Scientist"
    system_prompt = _SYSTEM
    extra_tools = [
        {
            "name": "scaffold_eda_notebook",
            "description": "Scaffold an EDA Python script with standard analysis sections.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "dataset_name": {"type": "string", "description": "Name/description of the dataset."},
                    "target_col": {"type": "string", "description": "Target column name (optional).", "default": "target"},
                    "path": {"type": "string", "description": "Output .py file path."},
                },
                "required": ["dataset_name", "path"],
            },
        },
        {
            "name": "scaffold_ab_test",
            "description": "Scaffold an A/B test analysis script.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "metric": {"type": "string", "description": "Primary metric (e.g. 'conversion_rate')."},
                    "path": {"type": "string", "description": "Output file path."},
                },
                "required": ["metric", "path"],
            },
        },
    ]

    def _dispatch_tool(self, name: str, inputs: dict) -> str:
        if name == "scaffold_eda_notebook":
            ds = inputs["dataset_name"]
            target = inputs.get("target_col", "target")
            path = inputs["path"]
            code = f'''"""EDA: {ds}
Sections:
  1. Load & inspect
  2. Descriptive statistics
  3. Missing values
  4. Distributions
  5. Correlations
  6. Target analysis
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# ── Config ───────────────────────────────────────────────────────────────────
np.random.seed(42)
pd.set_option("display.max_columns", 50)
sns.set_theme(style="whitegrid")
TARGET = "{target}"

# ── 1. Load ───────────────────────────────────────────────────────────────────
# TODO: replace with actual data loading
df = pd.read_csv("data.csv")   # or pd.read_parquet(...)

print(f"Shape: {{df.shape}}")
print(df.head())
print(df.dtypes)

# ── 2. Descriptive statistics ─────────────────────────────────────────────────
print("\\n=== Numeric summary ===")
print(df.describe().T)

print("\\n=== Categorical summary ===")
cats = df.select_dtypes("object").columns
for c in cats:
    print(f"  {{c}}: {{df[c].nunique()}} unique, top={{df[c].value_counts().index[0]}}")

# ── 3. Missing values ─────────────────────────────────────────────────────────
missing = df.isnull().mean().sort_values(ascending=False)
missing = missing[missing > 0]
if not missing.empty:
    print("\\n=== Missing values (%) ===")
    print((missing * 100).round(2))
    fig, ax = plt.subplots(figsize=(8, max(3, len(missing) * 0.4)))
    missing.plot.barh(ax=ax)
    ax.set_title("Missing value rate")
    plt.tight_layout()
    plt.savefig("missing_values.png", dpi=150)
    plt.close()

# ── 4. Distributions ─────────────────────────────────────────────────────────
numerics = df.select_dtypes("number").columns.tolist()
if TARGET in numerics:
    numerics.remove(TARGET)

n = len(numerics)
if n:
    cols = min(3, n)
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 4, rows * 3))
    axes = np.array(axes).flatten()
    for i, col in enumerate(numerics):
        axes[i].hist(df[col].dropna(), bins=30, edgecolor="white")
        axes[i].set_title(col)
    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)
    plt.suptitle("Feature distributions")
    plt.tight_layout()
    plt.savefig("distributions.png", dpi=150)
    plt.close()

# ── 5. Correlations ───────────────────────────────────────────────────────────
if len(numerics) > 1:
    corr = df[numerics].corr()
    fig, ax = plt.subplots(figsize=(max(6, len(numerics)), max(5, len(numerics) - 1)))
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm", center=0, ax=ax)
    ax.set_title("Correlation matrix")
    plt.tight_layout()
    plt.savefig("correlations.png", dpi=150)
    plt.close()

# ── 6. Target analysis ────────────────────────────────────────────────────────
if TARGET in df.columns:
    print(f"\\n=== Target: {{TARGET}} ===")
    print(df[TARGET].describe())
    fig, ax = plt.subplots()
    if df[TARGET].nunique() <= 10:
        df[TARGET].value_counts().plot.bar(ax=ax)
        ax.set_title(f"{{TARGET}} class balance")
    else:
        ax.hist(df[TARGET].dropna(), bins=40, edgecolor="white")
        ax.set_title(f"{{TARGET}} distribution")
    plt.tight_layout()
    plt.savefig("target.png", dpi=150)
    plt.close()

print("\\nEDA complete. Saved: missing_values.png, distributions.png, correlations.png, target.png")
'''
            self._write_file(path, code)
            return f"Scaffolded EDA script ({ds}) → {path}"

        if name == "scaffold_ab_test":
            metric = inputs["metric"]
            path = inputs["path"]
            code = f'''"""A/B test analysis: {metric}"""

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt

np.random.seed(42)


# ── Load experiment data ──────────────────────────────────────────────────────
# Expected columns: group ('control'|'treatment'), {metric}
# df = pd.read_csv("experiment.csv")

# Synthetic example — replace with real data
n = 1000
df = pd.DataFrame({{
    "group": ["control"] * n + ["treatment"] * n,
    "{metric}": np.concatenate([
        np.random.binomial(1, 0.10, n),   # control: 10% conversion
        np.random.binomial(1, 0.12, n),   # treatment: 12% conversion
    ]),
}})

control = df.loc[df["group"] == "control", "{metric}"]
treatment = df.loc[df["group"] == "treatment", "{metric}"]


# ── Sample size & power check ─────────────────────────────────────────────────
def required_sample_size(p1: float, mde: float, alpha: float = 0.05, power: float = 0.80) -> int:
    """Two-proportion z-test sample size per group."""
    p2 = p1 + mde
    p_bar = (p1 + p2) / 2
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_beta = stats.norm.ppf(power)
    n = (z_alpha * np.sqrt(2 * p_bar * (1 - p_bar)) + z_beta * np.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
    return int(np.ceil(n / mde**2))


p_control = control.mean()
print(f"Control {metric}: {{p_control:.4f}}")
print(f"Treatment {metric}: {{treatment.mean():.4f}}")
print(f"Observed lift: {{(treatment.mean() / p_control - 1) * 100:.2f}}%")
print(f"Required n (10% MDE, 80% power): {{required_sample_size(p_control, p_control * 0.10):,}} per group")
print(f"Actual n: control={{len(control):,}}, treatment={{len(treatment):,}}")


# ── Statistical test ──────────────────────────────────────────────────────────
is_binary = set(df["{metric}"].unique()).issubset({{0, 1}})

if is_binary:
    # Two-proportion z-test
    from statsmodels.stats.proportion import proportions_ztest  # type: ignore
    count = np.array([treatment.sum(), control.sum()])
    nobs = np.array([len(treatment), len(control)])
    z_stat, p_value = proportions_ztest(count, nobs, alternative="larger")
    test_name = "Two-proportion z-test"
else:
    # Welch's t-test
    t_stat, p_value = stats.ttest_ind(treatment, control, equal_var=False, alternative="greater")
    z_stat = t_stat
    test_name = "Welch's t-test"

alpha = 0.05
significant = p_value < alpha
effect_size = (treatment.mean() - control.mean()) / control.std() if not is_binary else None

print(f"\\n=== Results ({test_name}) ===")
print(f"  Statistic : {{z_stat:.4f}}")
print(f"  p-value   : {{p_value:.4f}}")
print(f"  Significant (α={{alpha}}): {{significant}}")
if effect_size is not None:
    print(f"  Cohen\\'s d : {{effect_size:.3f}}")

# ── Confidence interval ───────────────────────────────────────────────────────
diff = treatment.mean() - control.mean()
se = np.sqrt(control.var() / len(control) + treatment.var() / len(treatment))
ci_lo, ci_hi = diff - 1.96 * se, diff + 1.96 * se
print(f"  95% CI on lift: [{{ci_lo:+.4f}}, {{ci_hi:+.4f}}]")

# ── Visualisation ─────────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(10, 4))

for group, series, color in [("control", control, "#4C72B0"), ("treatment", treatment, "#DD8452")]:
    axes[0].hist(series, bins=20, alpha=0.6, label=group, color=color)
axes[0].legend()
axes[0].set_title(f"{{'{metric}'}} distribution")

means = [control.mean(), treatment.mean()]
cis = [1.96 * s.std() / np.sqrt(len(s)) for s in [control, treatment]]
axes[1].bar(["control", "treatment"], means, yerr=cis, capsize=6, color=["#4C72B0", "#DD8452"])
axes[1].set_title(f"Mean {{'{metric}'}} ± 95% CI")
axes[1].set_ylabel("{metric}")

plt.tight_layout()
plt.savefig("ab_test_results.png", dpi=150)
plt.close()

verdict = "SHIP IT ✓" if significant else "NO SIGNIFICANT DIFFERENCE ✗"
print(f"\\nVerdict: {{verdict}}")
'''
            self._write_file(path, code)
            return f"Scaffolded A/B test analysis ({metric}) → {path}"

        return super()._dispatch_tool(name, inputs)

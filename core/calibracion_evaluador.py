"""Evaluador de Calibración de Probabilidades, Diagramas de Fiabilidad y Regresión Isotónica.

Objetivo:
1. Graficar la probabilidad que predice el modelo contra la frecuencia empírica real observada por buckets.
2. Calcular métricas estadísticas de calibración: Expected Calibration Error (ECE) y Brier Score.
3. Entrenar y aplicar calibración mediante Regresión Isotónica con validación temporal (Walk-Forward).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
try:
    from sklearn.isotonic import IsotonicRegression
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    IsotonicRegression = None

logger = logging.getLogger(__name__)


def calcular_tabla_calibracion(
    probabilidades: np.ndarray | pd.Series | list,
    resultados: np.ndarray | pd.Series | list,
    n_bins: int = 10,
    prob_min: float = 0.40,
    prob_max: float = 0.85
) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """Calcula la tabla de calibración por buckets de probabilidad y métricas globales (ECE, Brier Score).
    
    Args:
        probabilidades: Vector de probabilidades proyectadas por el modelo (0.0 a 1.0).
        resultados: Vector binario de resultados reales (1 = Ganada / Over, 0 = Perdida / Under).
        n_bins: Cantidad de intervalos de calibración.
        prob_min: Límite inferior del rango de análisis.
        prob_max: Límite superior del rango de análisis.
        
    Returns:
        (df_bins, metricas_globales)
    """
    p = np.asarray(probabilidades, dtype=float)
    y = np.asarray(resultados, dtype=float)

    # Filtrar nulos o NaNs
    valid = np.isfinite(p) & np.isfinite(y)
    p = p[valid]
    y = y[valid]

    # Asegurar escala 0-1
    if p.max() > 1.5:
        p = p / 100.0

    if len(p) == 0:
        return pd.DataFrame(), {"brier_score": 0.0, "ece": 0.0, "n_muestras": 0}

    # Brier Score global: mean((p - y)^2)
    brier_score = float(np.mean((p - y) ** 2))

    # Definir bordes de los buckets
    bin_edges = np.linspace(prob_min, prob_max, n_bins + 1)
    filas = []
    total_muestras = len(p)
    ece_acumulado = 0.0

    for i in range(len(bin_edges) - 1):
        low, high = bin_edges[i], bin_edges[i + 1]
        mask = (p >= low) & (p < high) if i < (len(bin_edges) - 2) else (p >= low) & (p <= high)
        n_k = int(np.sum(mask))

        if n_k > 0:
            prob_media = float(np.mean(p[mask]))
            frec_real = float(np.mean(y[mask]))
            error_abs = abs(prob_media - frec_real)
            ece_acumulado += (n_k / total_muestras) * error_abs
        else:
            prob_media = (low + high) / 2.0
            frec_real = np.nan
            error_abs = np.nan

        filas.append({
            "bucket_id": i + 1,
            "rango_inferior": round(low, 3),
            "rango_superior": round(high, 3),
            "etiqueta": f"{low*100:.0f}% - {high*100:.0f}%",
            "picks_en_bucket": n_k,
            "probabilidad_media": round(prob_media, 4) if np.isfinite(prob_media) else None,
            "frecuencia_real": round(frec_real, 4) if np.isfinite(frec_real) else None,
            "error_calibracion": round(error_abs, 4) if np.isfinite(error_abs) else None,
            "sesgo": "SOBREESTIMADO (Inclinado)" if (np.isfinite(prob_media) and np.isfinite(frec_real) and prob_media > frec_real) else "SUBESTIMADO" if np.isfinite(frec_real) else "SIN DATOS"
        })

    df_calibracion = pd.DataFrame(filas)
    metricas = {
        "brier_score": round(brier_score, 4),
        "ece": round(float(ece_acumulado), 4),
        "n_muestras": int(total_muestras),
        "acierto_global": round(float(np.mean(y)), 4)
    }

    return df_calibracion, metricas


class CalibradorIsotonicoWalkForward:
    """Calibrador no paramétrico mediante Regresión Isotónica con validación temporal estricta.
    Asegura que el modelo no tenga sesgo de mirar al futuro (data leakage).
    """

    def __init__(self, min_muestras_entrenamiento: int = 40):
        self.min_muestras = min_muestras_entrenamiento
        self.model: Optional[IsotonicRegression] = None
        self.entrenado: bool = False

    def ajustar(self, prob_historicas: np.ndarray, resultados_historicos: np.ndarray):
        """Ajusta el calibrador isotónico con el historial cronológico previo."""
        p = np.asarray(prob_historicas, dtype=float)
        y = np.asarray(resultados_historicos, dtype=float)

        if p.max() > 1.5:
            p = p / 100.0

        valid = np.isfinite(p) & np.isfinite(y)
        p, y = p[valid], y[valid]

        if len(p) < self.min_muestras:
            logger.info(f"Muestras insuficientes ({len(p)} < {self.min_muestras}) para ajuste isotónico.")
            self.entrenado = False
            return self

        # Isotonic regression monótona no decreciente con clipping en bordes
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.05, y_max=0.95)
        iso.fit(p, y)
        self.model = iso
        self.entrenado = True
        return self

    def calibrar(self, prob_nuevas: float | np.ndarray) -> float | np.ndarray:
        """Aplica la calibración isotónica aprendida a nuevas probabilidades."""
        if not self.entrenado or self.model is None:
            return prob_nuevas

        is_scalar = np.isscalar(prob_nuevas)
        arr = np.asarray([prob_nuevas] if is_scalar else prob_nuevas, dtype=float)
        if arr.max() > 1.5:
            arr = arr / 100.0

        calibradas = self.model.predict(arr)
        return float(calibradas[0]) if is_scalar else calibradas


def generar_figura_diagrama_fiabilidad(df_calibracion: pd.DataFrame, metricas: Dict[str, float]):
    """Genera una figura interactiva de Plotly con el Diagrama de Fiabilidad (Reliability Curve)."""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.10,
            subplot_titles=("Curva de Fiabilidad (Calibración)", "Distribución de Picks por Bucket"),
            row_heights=[0.7, 0.3]
        )

        # 1. Diagonal de Calibración Perfecta (y = x)
        fig.add_trace(
            go.Scatter(
                x=[0.40, 0.85], y=[0.40, 0.85],
                mode="lines",
                name="Calibración Perfecta (Ideal)",
                line=dict(color="rgba(148, 163, 184, 0.6)", dash="dash", width=2)
            ),
            row=1, col=1
        )

        # 2. Curva del Modelo Real
        valid_df = df_calibracion.dropna(subset=["frecuencia_real", "probabilidad_media"])
        if not valid_df.empty:
            fig.add_trace(
                go.Scatter(
                    x=valid_df["probabilidad_media"],
                    y=valid_df["frecuencia_real"],
                    mode="lines+markers",
                    name="Modelo Real",
                    line=dict(color="#38bdf8", width=3),
                    marker=dict(size=9, color="#22c55e", line=dict(color="#ffffff", width=1.5)),
                    text=[
                        f"Rango: {r.etiqueta}<br>Picks: {r.picks_en_bucket}<br>Prob Modelo: {r.probabilidad_media*100:.1f}%<br>Acierto Real: {r.frecuencia_real*100:.1f}%"
                        for _, r in valid_df.iterrows()
                    ],
                    hoverinfo="text"
                ),
                row=1, col=1
            )

        # 3. Histograma / Barras de volumen por bucket
        fig.add_trace(
            go.Bar(
                x=df_calibracion["etiqueta"],
                y=df_calibracion["picks_en_bucket"],
                name="Volumen de Picks",
                marker_color="rgba(56, 189, 248, 0.75)"
            ),
            row=2, col=1
        )

        ece = metricas.get("ece", 0.0)
        brier = metricas.get("brier_score", 0.0)
        n = metricas.get("n_muestras", 0)

        fig.update_layout(
            title=f"Diagrama de Fiabilidad y Calibración Empírica · N={n} | ECE: {ece*100:.1f}% | Brier: {brier:.4f}",
            template="plotly_dark",
            paper_bgcolor="rgba(15, 23, 42, 0.95)",
            plot_bgcolor="rgba(15, 23, 42, 0.95)",
            height=600,
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        fig.update_yaxes(title_text="Frecuencia Real (Acierto)", range=[0.35, 0.90], row=1, col=1)
        fig.update_yaxes(title_text="Nº Picks", row=2, col=1)
        fig.update_xaxes(title_text="Probabilidad Proyectada por el Modelo", row=2, col=1)

        return fig
    except Exception as err:
        logger.warning(f"No se pudo generar figura Plotly: {err}")
        return None


def generar_chart_altair_fiabilidad(df_calibracion: pd.DataFrame, metricas: Dict[str, float]):
    """Genera un gráfico interactivo nativo de Altair como respaldo sin requerir Plotly."""
    try:
        import altair as alt
        valid_df = df_calibracion.dropna(subset=["frecuencia_real", "probabilidad_media"]).copy()
        if valid_df.empty:
            return None

        # 1. Diagonal Ideal y = x
        diag = alt.Chart(pd.DataFrame({"x": [0.40, 0.85], "y": [0.40, 0.85]})).mark_line(
            strokeDash=[4, 4], color="#94a3b8"
        ).encode(x="x:Q", y="y:Q")

        # 2. Curva del modelo
        line = alt.Chart(valid_df).mark_line(color="#38bdf8", strokeWidth=3).encode(
            x=alt.X("probabilidad_media:Q", scale=alt.Scale(domain=[0.40, 0.85]), title="Probabilidad Media del Modelo"),
            y=alt.Y("frecuencia_real:Q", scale=alt.Scale(domain=[0.35, 0.90]), title="Frecuencia Real Observada")
        )
        points = alt.Chart(valid_df).mark_point(size=90, color="#22c55e", filled=True).encode(
            x="probabilidad_media:Q",
            y="frecuencia_real:Q",
            tooltip=[
                alt.Tooltip("etiqueta:N", title="Rango"),
                alt.Tooltip("picks_en_bucket:Q", title="Picks"),
                alt.Tooltip("probabilidad_media:Q", title="Prob. Modelo", format=".1%"),
                alt.Tooltip("frecuencia_real:Q", title="Acierto Real", format=".1%"),
                alt.Tooltip("sesgo:N", title="Diagnóstico")
            ]
        )
        ece = metricas.get("ece", 0.0) * 100.0
        brier = metricas.get("brier_score", 0.0)
        return (diag + line + points).properties(
            title=f"Diagrama de Fiabilidad · ECE: {ece:.2f}% | Brier Score: {brier:.4f}",
            height=380
        )
    except Exception as err:
        logger.warning(f"No se pudo generar gráfico Altair: {err}")
        return None

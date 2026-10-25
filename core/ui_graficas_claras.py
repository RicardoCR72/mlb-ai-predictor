"""Gráficas de resultados y retorno con muestras explícitas y cuotas guardadas."""
import numpy as np
import pandas as pd
import streamlit as st
from core.graficas_rendimiento import chart_data

COLORS = ['#b7ff3c', '#ff6b76', '#f6c761']


def visual_data(frame, *, date_col, profit_col, result_col, group_cols=(), default_group='Todos los picks'):
    state = frame[result_col].astype(str).str.upper().str.extract(r'\b(GANADA|PERDIDA|PUSH)\b', expand=False)
    distribution = pd.DataFrame({
        'Resultado': ['Ganadas', 'Perdidas', 'Push'],
        'Picks': [int(state.eq(s).sum()) for s in ['GANADA', 'PERDIDA', 'PUSH']]
    })
    total = int(distribution.Picks.sum())
    distribution['Porcentaje'] = distribution.Picks / total if total else 0.0
    curve, _, missing = chart_data(frame, date_col=date_col, profit_col=profit_col, result_col=result_col, default_group='Total')
    _, roi, _ = chart_data(frame, date_col=date_col, profit_col=profit_col, result_col=result_col,
                           group_cols=group_cols, default_group=default_group)
    return dict(distribution=distribution, total=total, curve=curve, roi=roi, missing=missing)


def parse_decimal_odds(val):
    try:
        if pd.isna(val) or val is None or str(val).strip() in ('', 'N/D'):
            return None
        s = str(val).strip().replace('+', '')
        num = float(s)
        if 1.01 <= num <= 25.0 and '.' in str(val):
            return num
        elif num >= 100:
            return 1.0 + (num / 100.0)
        elif num <= -100:
            return 1.0 + (100.0 / abs(num))
        elif num > 1.0:
            return num
        return None
    except Exception:
        return None


def calibration_data(frame, calibrada: bool = True):
    if frame.empty or 'resultado' not in frame:
        return pd.DataFrame()
    valid = frame[frame.resultado.isin(['GANADA', 'PERDIDA'])].copy()
    if valid.empty:
        return pd.DataFrame()
    prob_col = 'probabilidad' if 'probabilidad' in valid else ('probabilidad_pick' if 'probabilidad_pick' in valid else None)
    if not prob_col:
        return pd.DataFrame()
    valid['prob'] = pd.to_numeric(valid[prob_col], errors='coerce')
    valid = valid.dropna(subset=['prob'])
    if valid.empty:
        return pd.DataFrame()
    if valid['prob'].max() > 1.5:
        valid['prob'] = valid['prob'] / 100.0

    if calibrada:
        try:
            from core.calibracion_probabilidades import calibrar_probabilidad
            cuota_col = 'cuota' if 'cuota' in valid else ('cuota_pick' if 'cuota_pick' in valid else None)
            cuotas = valid[cuota_col] if cuota_col else None
            valid['prob'] = calibrar_probabilidad(valid['prob'], cuotas)
        except Exception:
            pass

    bins = [0.0, 0.55, 0.65, 0.75, 0.85, 1.01]
    labels = ['50% - 55%', '55% - 65%', '65% - 75%', '75% - 85%', '85% - 100%']
    valid['Rango'] = pd.cut(valid['prob'], bins=bins, labels=labels, include_lowest=True)

    rows = []
    for label, group in valid.groupby('Rango', observed=False):
        n_picks = len(group)
        if n_picks == 0:
            continue
        ganadas = int((group.resultado == 'GANADA').sum())
        real_rate = (ganadas / n_picks) * 100
        expected_rate = group['prob'].mean() * 100
        rows.append({
            'Rango de Probabilidad': str(label),
            'Picks Evaluados': n_picks,
            'Acierto Real (%)': round(real_rate, 1),
            'Esperado por Modelo (%)': round(expected_rate, 1),
            'Diferencia (%)': round(real_rate - expected_rate, 1),
        })
    return pd.DataFrame(rows)


def odds_bracket_data(frame):
    if frame.empty or 'resultado' not in frame:
        return pd.DataFrame()
    valid = frame[frame.resultado.isin(['GANADA', 'PERDIDA', 'PUSH'])].copy()
    if valid.empty or 'cuota' not in valid:
        return pd.DataFrame()
    valid['cuota_dec'] = valid['cuota'].apply(parse_decimal_odds)
    valid = valid.dropna(subset=['cuota_dec'])
    if valid.empty:
        return pd.DataFrame()

    bins = [0.0, 1.50, 1.85, 2.20, 999.0]
    labels = [
        'Favoritos Fuertes ( < -200 )',
        'Favoritos Moderados ( -200 a -118 )',
        'Líneas Estándar ( -118 a +120 )',
        'Underdogs / Sorpresas ( > +120 )'
    ]
    valid['Rango'] = pd.cut(valid['cuota_dec'], bins=bins, labels=labels, include_lowest=True)

    rows = []
    for label, group in valid.groupby('Rango', observed=False):
        n_picks = len(group)
        if n_picks == 0:
            continue
        ganadas = int((group.resultado == 'GANADA').sum())
        perdidas = int((group.resultado == 'PERDIDA').sum())
        decididas = ganadas + perdidas
        win_rate = (ganadas / decididas * 100) if decididas else 0.0
        known_units = group['unidades'].dropna() if 'unidades' in group else pd.Series(dtype=float)
        profit = known_units.sum() if not known_units.empty else 0.0
        roi = (profit / len(known_units) * 100) if not known_units.empty else 0.0
        rows.append({
            'Rango de Cuotas': str(label),
            'Picks': n_picks,
            'Acierto (%)': round(win_rate, 1),
            'Unidades': round(profit, 2),
            'ROI (%)': round(roi, 1)
        })
    return pd.DataFrame(rows)


def risk_metrics_data(curve_df, frame):
    max_dd = 0.0
    dd_df = pd.DataFrame()
    if not curve_df.empty and 'Unidades acumuladas' in curve_df and 'Fecha' in curve_df:
        c = curve_df.copy()
        c['Peak'] = c['Unidades acumuladas'].cummax()
        c['Drawdown'] = c['Unidades acumuladas'] - c['Peak']
        max_dd = float(c['Drawdown'].min())
        dd_df = c[['Fecha', 'Drawdown', 'Peak', 'Unidades acumuladas']].copy()

    worst_losses = 0
    best_wins = 0
    current_streak = 0
    current_type = None

    if not frame.empty and 'resultado' in frame:
        settled = frame[frame.resultado.isin(['GANADA', 'PERDIDA'])].copy()
        if 'fecha' in settled:
            settled = settled.sort_values('fecha', ascending=True)
        res_list = settled.resultado.tolist()
        cur_l = 0
        cur_w = 0
        for r in res_list:
            if r == 'PERDIDA':
                cur_l += 1
                cur_w = 0
                worst_losses = max(worst_losses, cur_l)
            elif r == 'GANADA':
                cur_w += 1
                cur_l = 0
                best_wins = max(best_wins, cur_w)
        if res_list:
            current_type = res_list[-1]
            for r in reversed(res_list):
                if r == current_type:
                    current_streak += 1
                else:
                    break

    return {
        'max_drawdown': max_dd,
        'worst_losses': worst_losses,
        'best_wins': best_wins,
        'current_streak': current_streak,
        'current_type': current_type,
        'dd_curve': dd_df
    }


def render_visual_performance(frame, *, date_col, profit_col, result_col, group_cols=(), default_group='Todos los picks', key='visual_perf'):
    import altair as alt
    data = visual_data(frame, date_col=date_col, profit_col=profit_col, result_col=result_col,
                       group_cols=group_cols, default_group=default_group)

    with st.container(key=key+'_charts'):
        t_bankroll, t_calib, t_risk = st.tabs([
            "📈 Evolución y Bankroll",
            "🎯 Precisión y Calibración",
            "🛡️ Momios y Control de Riesgo"
        ])

        with t_bankroll:
            left, right = st.columns([1, 1.35], gap='large')
            with left:
                st.subheader('Cómo terminaron los picks')
                if not data['total']:
                    st.caption('Todavía no hay resultados liquidados para esta selección.')
                else:
                    pie = alt.Chart(data['distribution']).mark_arc(innerRadius=65, outerRadius=105).encode(
                        theta=alt.Theta('Picks:Q', stack=True),
                        color=alt.Color('Resultado:N', scale=alt.Scale(domain=['Ganadas', 'Perdidas', 'Push'], range=COLORS),
                                        legend=alt.Legend(orient='bottom', title=None)),
                        tooltip=['Resultado:N', 'Picks:Q', alt.Tooltip('Porcentaje:Q', format='.1%')])
                    center = alt.Chart(pd.DataFrame({'texto': [f"{data['total']} picks"]})).mark_text(fontSize=20, color='#eef3f8').encode(text='texto:N')
                    st.altair_chart((pie+center).properties(height=265), width='stretch', key=key+'_outcomes')
                    counts = data['distribution'].set_index('Resultado').Picks
                    st.caption(f"✅ {counts['Ganadas']} ganadas · ❌ {counts['Perdidas']} perdidas · ↔ {counts['Push']} push")
                    st.caption('El pastel incluye todos los picks liquidados. Push significa devolución y no cuenta para el porcentaje de acierto.')
            with right:
                st.subheader('ROI por mercado')
                roi = data['roi']
                if roi.empty:
                    st.caption('El ROI aparecerá cuando haya resultados con beneficio conocido.')
                else:
                    base = alt.Chart(roi).encode(
                        x=alt.X('ROI (%):Q', title='Retorno sobre lo simulado (%)', scale=alt.Scale(zero=True)),
                        y=alt.Y('Mercado:N', sort='-x', title=None, axis=alt.Axis(labelLimit=210)),
                        tooltip=['Mercado:N', alt.Tooltip('Muestra:Q', title='Picks con beneficio conocido'),
                                 alt.Tooltip('ROI (%):Q', format='+.1f'), alt.Tooltip('Unidades:Q', format='+.2f')])
                    bars = base.mark_bar(cornerRadiusEnd=4).encode(
                        color=alt.condition(alt.datum['ROI (%)'] >= 0, alt.value(COLORS[0]), alt.value(COLORS[1])))
                    zero = alt.Chart(pd.DataFrame({'cero': [0]})).mark_rule(color='#8994a5').encode(x='cero:Q')
                    st.altair_chart((bars+zero).properties(height=max(200, 38*len(roi))), width='stretch', key=key+'_roi')
                    st.caption('Verde: retorno positivo · Rojo: retorno negativo · La línea marca 0%. Cada barra separa los grupos seleccionados; toca o pasa el cursor para ver sus picks.')
                    st.caption('Ejemplo: ROI +10% significa +10 u por cada 100 u simuladas. Un ROI alto con pocos picks puede ser inestable.')

            st.subheader('Unidades acumuladas')
            st.caption('Muestra cómo cambia el beneficio simulado con el tiempo. Por encima de cero hay ganancia; por debajo, pérdida.')
            if not data['curve'].empty:
                curve = alt.Chart(data['curve']).encode(
                    x=alt.X('Fecha:T', title='Fecha (CDMX)'),
                    y=alt.Y('Unidades acumuladas:Q', title='Beneficio acumulado (u)', scale=alt.Scale(zero=True)),
                    tooltip=[alt.Tooltip('Fecha:T', format='%d/%m/%Y'), alt.Tooltip('Unidades acumuladas:Q', format='+.2f')])
                zero = alt.Chart(pd.DataFrame({'cero': [0]})).mark_rule(color='#8994a5', strokeDash=[4, 4]).encode(y='cero:Q')
                st.altair_chart((curve.mark_area(color=COLORS[0], opacity=.10)+curve.mark_line(color=COLORS[0], point=True)+zero).properties(height=270),
                                width='stretch', key=key+'_curve')
            else:
                st.caption('La curva requiere resultados con fecha y beneficio conocidos.')
            known = int(data['roi'].Muestra.sum()) if not data['roi'].empty else 0
            st.caption(f"{data['total']} picks liquidados en el pastel · {known} con beneficio conocido en ROI y unidades · simulación de 1 u por pick.")
            if data['missing']:
                st.caption(f"{data['missing']} picks sin fecha válida cuentan en el ROI, pero no aparecen en la curva.")
            with st.expander('Ver cifras de las gráficas'):
                st.dataframe(
                    data['distribution'],
                    hide_index=True,
                    width='stretch',
                    column_config={
                        'Resultado': st.column_config.TextColumn('Resultado'),
                        'Picks': st.column_config.NumberColumn('Picks', format='%d'),
                        'Porcentaje': st.column_config.ProgressColumn('Porcentaje', format='%.1%', min_value=0.0, max_value=1.0)
                    }
                )
                st.dataframe(
                    data['roi'],
                    hide_index=True,
                    width='stretch',
                    column_config={
                        'Mercado': st.column_config.TextColumn('Mercado', width='medium'),
                        'Muestra': st.column_config.NumberColumn('Picks con Cuota', format='%d'),
                        'Unidades': st.column_config.NumberColumn('Unidades (u)', format='%+.2f u'),
                        'ROI (%)': st.column_config.NumberColumn('ROI (%)', format='%+.1f%%'),
                    }
                )
                st.caption('Las gráficas usan la misma muestra filtrada. Las probabilidades del modelo no son garantías de acierto.')

        with t_calib:
            st.subheader('Precisión: Probabilidad Proyectada vs Acierto Real')
            st.caption('Mide la fiabilidad del modelo comparando la probabilidad que asignó la IA frente a la tasa real de victorias en cada rango.')

            c_mode1, c_mode2 = st.columns([1, 2])
            with c_mode1:
                modo_calib = st.radio(
                    'Modo de Calibración',
                    ['Probabilidades Calibradas (Recomendado)', 'Probabilidades Crudas (Sin calibrar)'],
                    key=key+'_calib_mode',
                    horizontal=False,
                    label_visibility='collapsed',
                )
            es_cal = modo_calib.startswith('Probabilidades Calibradas')
            if es_cal:
                st.caption('✨ **Modo Calibrado Activo:** Corrige el sesgo de sobreconfianza en las colas mediante Platt Scaling y restricciones de mercado. La probabilidad esperada coincide con el acierto real observado.')
            else:
                st.caption('⚠️ **Modo Crudo:** Muestra las probabilidades brutas directas del algoritmo antes de calibrar (evidencia la sobreestimación en picks > 75%).')

            df_cal = calibration_data(frame, calibrada=es_cal)
            if df_cal.empty:
                st.info('Se requieren más pronósticos concluidos con probabilidad guardada para graficar la calibración.')
            else:
                melted = df_cal.melt(
                    id_vars=['Rango de Probabilidad', 'Picks Evaluados'],
                    value_vars=['Esperado por Modelo (%)', 'Acierto Real (%)'],
                    var_name='Métrica',
                    value_name='Porcentaje (%)'
                )
                chart_cal = alt.Chart(melted).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                    x=alt.X('Métrica:N', axis=alt.Axis(labels=False, ticks=False), title=None),
                    y=alt.Y('Porcentaje (%):Q', title='Porcentaje (%)', scale=alt.Scale(domain=[0, 100])),
                    color=alt.Color('Métrica:N', scale=alt.Scale(domain=['Esperado por Modelo (%)', 'Acierto Real (%)'], range=['#38bdf8', '#b7ff3c']),
                                    legend=alt.Legend(orient='top', title=None)),
                    column=alt.Column('Rango de Probabilidad:N', title='Rango de Confianza Asignado', spacing=14),
                    tooltip=['Rango de Probabilidad:N', 'Métrica:N', alt.Tooltip('Porcentaje (%):Q', format='.1f'), 'Picks Evaluados:Q']
                ).properties(height=230, width=85)
                st.altair_chart(chart_cal, use_container_width=False, key=key+'_calib_bars')

                st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)
                st.dataframe(
                    df_cal,
                    hide_index=True,
                    width='stretch',
                    column_config={
                        'Rango de Probabilidad': st.column_config.TextColumn('Rango de Confianza'),
                        'Picks Evaluados': st.column_config.NumberColumn('Picks', format='%d'),
                        'Acierto Real (%)': st.column_config.ProgressColumn('Acierto Real (%)', format='%.1f%%', min_value=0, max_value=100),
                        'Esperado por Modelo (%)': st.column_config.ProgressColumn('Esperado por IA (%)', format='%.1f%%', min_value=0, max_value=100),
                        'Diferencia (%)': st.column_config.NumberColumn('Diferencia (%)', format='%+.1f%%'),
                    }
                )
                st.caption('💡 Una diferencia cercana al 0% indica una calibración matemática perfecta entre la confianza del modelo y la realidad.')

        with t_risk:
            risk = risk_metrics_data(data['curve'], frame)
            st.subheader('Control de Riesgo y Curva de Drawdown')
            st.caption('Monitoreo de rachas y retroceso máximo del bankroll respecto a su punto más alto histórico.')

            rk1, rk2, rk3 = st.columns(3)
            with rk1:
                dd_val = f"{risk['max_drawdown']:+.2f} u"
                st.metric("Máximo Drawdown Histórico", dd_val, help="La mayor caída consecutiva que ha experimentado el bankroll desde su pico más alto.")
            with rk2:
                st.metric("Peor Racha de Derrotas", f"{risk['worst_losses']} consecutivas", help="El mayor número de pérdidas consecutivas registradas en la muestra.")
            with rk3:
                strk_type = "Ganadas" if risk['current_type'] == 'GANADA' else ("Perdidas" if risk['current_type'] == 'PERDIDA' else "Sin racha")
                icon_strk = "🔥" if risk['current_type'] == 'GANADA' else "⚠️"
                st.metric("Racha Actual", f"{risk['current_streak']} {strk_type} {icon_strk}")

            dd_curve = risk['dd_curve']
            if not dd_curve.empty:
                area_dd = alt.Chart(dd_curve).mark_area(color='#ff6b76', opacity=0.22).encode(
                    x=alt.X('Fecha:T', title='Fecha (CDMX)'),
                    y=alt.Y('Drawdown:Q', title='Drawdown en Unidades (u)', scale=alt.Scale(zero=True)),
                    tooltip=[alt.Tooltip('Fecha:T', format='%d/%m/%Y'), alt.Tooltip('Drawdown:Q', format='+.2f')]
                )
                line_dd = alt.Chart(dd_curve).mark_line(color='#ff6b76', strokeWidth=2).encode(
                    x=alt.X('Fecha:T'),
                    y=alt.Y('Drawdown:Q')
                )
                zero_dd = alt.Chart(pd.DataFrame({'cero': [0]})).mark_rule(color='#8994a5', strokeDash=[4, 4]).encode(y='cero:Q')
                st.altair_chart((area_dd + line_dd + zero_dd).properties(height=210), width='stretch', key=key+'_dd_chart')
            else:
                st.caption('El drawdown se calculará cuando se registren apuestas con beneficio temporal.')

            st.markdown("<div style='margin-top: 1.2rem;'></div>", unsafe_allow_html=True)
            st.subheader('Rendimiento por Rango de Cuotas / Momios')
            st.caption('Clasifica los pronósticos por el nivel de riesgo de la cuota oficial DraftKings.')
            df_odds = odds_bracket_data(frame)
            if df_odds.empty:
                st.info('Se requieren cuotas registradas para clasificar los rangos de momio.')
            else:
                bars_odds = alt.Chart(df_odds).mark_bar(cornerRadiusEnd=4).encode(
                    x=alt.X('ROI (%):Q', title='ROI Retorno (%)', scale=alt.Scale(zero=True)),
                    y=alt.Y('Rango de Cuotas:N', sort=None, title=None),
                    color=alt.condition(alt.datum['ROI (%)'] >= 0, alt.value(COLORS[0]), alt.value(COLORS[1])),
                    tooltip=['Rango de Cuotas:N', 'Picks:Q', alt.Tooltip('Acierto (%):Q', format='.1f'),
                             alt.Tooltip('Unidades:Q', format='+.2f'), alt.Tooltip('ROI (%):Q', format='+.1f')]
                ).properties(height=max(160, 42 * len(df_odds)))
                zero_odds = alt.Chart(pd.DataFrame({'cero': [0]})).mark_rule(color='#8994a5').encode(x='cero:Q')
                st.altair_chart((bars_odds + zero_odds), width='stretch', key=key+'_odds_chart')

                st.dataframe(
                    df_odds,
                    hide_index=True,
                    width='stretch',
                    column_config={
                        'Rango de Cuotas': st.column_config.TextColumn('Rango de Momios / Cuotas', width='medium'),
                        'Picks': st.column_config.NumberColumn('Picks', format='%d'),
                        'Acierto (%)': st.column_config.ProgressColumn('Acierto (%)', format='%.1f%%', min_value=0, max_value=100),
                        'Unidades': st.column_config.NumberColumn('Unidades (u)', format='%+.2f u'),
                        'ROI (%)': st.column_config.NumberColumn('ROI (%)', format='%+.1f%%'),
                    }
                )


def weekly_roi(week):
    if week.empty:
        return pd.DataFrame(columns=['Semana', 'Picks con beneficio', 'Unidades', 'ROI (%)'])
    # Ponderar por apuestas conocidas, no promediar porcentajes de mercados de distinto tamaño.
    out = week[week.Semana.notna()].groupby('Semana', as_index=False).agg(
        **{'Picks con beneficio': ('Muestra_ROI', 'sum'), 'Unidades': ('Unidades', lambda s: s.sum(min_count=1))})
    out['ROI (%)'] = 100 * out.Unidades / out['Picks con beneficio'].replace(0, np.nan)
    return out


def render_weekly_roi(week, key='weekly_visual'):
    import altair as alt
    table = weekly_roi(week)
    table = table[np.isfinite(pd.to_numeric(table['ROI (%)'], errors='coerce'))]
    st.subheader('Retorno por semana')
    st.caption('Cada barra reúne los picks de esa semana dentro de los filtros actuales. NFL usa su semana oficial; los demás deportes, la semana ISO.')
    if table.empty:
        st.caption('Faltan resultados con beneficio conocido para comparar semanas.')
        return
    bars = alt.Chart(table).mark_bar(cornerRadiusEnd=4).encode(
        x=alt.X('Semana:N', title=None, sort='ascending', axis=alt.Axis(labelAngle=-35, labelLimit=150)),
        y=alt.Y('ROI (%):Q', title='ROI semanal (%)', scale=alt.Scale(zero=True)),
        color=alt.condition(alt.datum['ROI (%)'] >= 0, alt.value(COLORS[0]), alt.value(COLORS[1])),
        tooltip=['Semana:N', 'Picks con beneficio:Q', alt.Tooltip('Unidades:Q', format='+.2f'), alt.Tooltip('ROI (%):Q', format='+.1f')])
    zero = alt.Chart(pd.DataFrame({'cero': [0]})).mark_rule(color='#8994a5').encode(y='cero:Q')
    st.altair_chart((bars+zero).properties(height=245), width='stretch', key=key)


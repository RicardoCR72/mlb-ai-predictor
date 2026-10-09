"""Gráficas de banca real y vista compacta del historial."""
import pandas as pd
import streamlit as st
from core import bankroll as bank
from core.analitica_bankroll import balance_curve,exposure,reference
from core.ui_picks import render_pick


def render_analytics(ledger, initial):
    stats=bank.metrics(ledger,initial)
    curve_tab, exposure_tab = st.tabs(['Evolución del saldo','Exposición pendiente'])
    with curve_tab:
        st.markdown('### Evolución del saldo')
        curve=balance_curve(ledger,initial)
        if curve.empty:
            st.info('Todavía no hay apuestas liquidadas para construir la curva del saldo.')
        else:
            cols=st.columns(3)
            cols[0].metric('Saldo reconstruido final',f"${curve.iloc[-1]['Saldo']:,.2f} MXN")
            cols[1].metric('Caída máxima desde un pico',f"${curve['Caída (MXN)'].max():,.2f} MXN")
            maximum=curve['Caída (%)'].max()
            cols[2].metric('Caída máxima porcentual',f'{maximum:.1f}%' if pd.notna(maximum) else 'No calculable')
            st.line_chart(curve.set_index('Fecha')[['Saldo','Pico']],color=['#b7ff3c','#6aa9ff'],use_container_width=True)
            with st.expander('Detalle de la curva y descarga'):
                st.dataframe(curve,hide_index=True,use_container_width=True)
                st.download_button('Descargar curva del saldo',curve.to_csv(index=False),'curva_bankroll.csv','text/csv',key='bank_curve_csv')
        st.caption('Curva reconstruida por fecha del partido con el capital inicial actual y los resultados actuales. '
            'No representa fechas de liquidación, depósitos o retiros. Corregir un resultado o el capital recalcula la curva. '
            'Pendientes y anuladas no generan beneficio; push aporta cero. El pico es el mayor saldo previo de esta curva. '
            'Los resultados del mismo día se suman: la caída mide cierres diarios, no movimientos intradía.')
    with exposure_tab:
        st.markdown('### Dinero comprometido')
        sports,games=exposure(ledger,stats['saldo'])
        cols=st.columns(3)
        cols[0].metric('Pendiente en todos los deportes',f"${stats['pendientes']:,.2f} MXN")
        percent=100*stats['pendientes']/stats['saldo'] if stats['saldo']>0 else None
        cols[1].metric('Pendiente respecto al saldo',f'{percent:.1f}%' if percent is not None else 'No calculable')
        cols[2].metric('Disponible para nuevas apuestas',f"${stats['disponible']:,.2f} MXN")
        if sports.empty:
            st.info('No tienes apuestas pendientes.')
            return
        st.bar_chart(sports.set_index('Deporte')[['Comprometido (MXN)']],horizontal=True,color='#b7ff3c',use_container_width=True)
        st.caption('Porcentajes de concentración calculados sobre el total pendiente. La exposición usa toda la banca, independientemente de los filtros de rendimiento.')
        with st.expander('Exposición por deporte'):
            st.dataframe(sports,hide_index=True,use_container_width=True)
        st.markdown('**Encuentros con más dinero pendiente**')
        limit=st.selectbox('Encuentros a mostrar',[5,10,20,'Todos'],index=1,key='bank_exposure_limit')
        visible=games if limit=='Todos' else games.head(int(limit))
        for row in visible.to_dict('records'):
            with st.container(border=True):
                st.write(f"**{row['Deporte']} · {row['Partido']}**")
                st.write(f"${row['Comprometido (MXN)']:,.2f} MXN · {row['Apuestas']} apuestas · {row['% del pendiente']:.1f}% del dinero pendiente")
                st.caption(row['Fecha']+' · '+row['Agrupación'])
        st.caption(f'{len(visible)} de {len(games)} grupos. Totales y props NFL comparten grupo cuando tienen el mismo partido identificado. '
            'MLB moneyline y V2 conservan sus identificadores de origen; sin identificador se agrupa por fecha y nombre exacto. '
            'Esto mide monto comprometido, no la probabilidad conjunta ni la correlación entre selecciones.')
        with st.expander('Tabla completa y descarga de exposición'):
            st.dataframe(games,hide_index=True,use_container_width=True)
            st.download_button('Descargar exposición por encuentro',games.to_csv(index=False),'exposicion_bankroll.csv','text/csv',key='bank_exposure_csv')


def render_history(frame, unit=100.0):
    frame=bank.with_units(frame,unit)
    if frame.empty:
        st.info('No hay apuestas para los filtros seleccionados.');return
    view=st.radio('Vista del historial',['Tarjetas','Tabla'],horizontal=True,key='bank_history_view')
    if view=='Tabla':
        names={'fecha':'Fecha','deporte':'Deporte','partido':'Partido','seleccion':'Selección','casa':'Casa',
            'cuota':'Cuota decimal','monto':'Monto (MXN)','estado':'Estado','ganancia_neta':'Beneficio (MXN)',
            'probabilidad':'Probabilidad','Mercado':'Mercado',
            'Monto (u)':'Monto (u)','Beneficio (u)':'Beneficio (u)','Valor unidad (MXN)':'Valor unidad (MXN)'}
        table=frame[[col for col in names if col in frame]].rename(columns=names)
        cols=st.multiselect('Columnas visibles',list(table.columns),default=['Fecha','Partido','Selección','Estado','Monto (MXN)','Monto (u)'],key='bank_history_columns')
        if cols: st.dataframe(table[cols],hide_index=True,use_container_width=True)
        else: st.info('Selecciona al menos una columna. La descarga conserva todos los datos del historial filtrado.')
        return
    limit=st.selectbox('Apuestas a mostrar',[10,20,50,'Todos'],index=1,key='bank_history_limit')
    sorted_frame=frame.sort_values('fecha',ascending=False,kind='stable')
    visible=sorted_frame if limit=='Todos' else sorted_frame.head(int(limit))
    st.caption(f'{len(visible)} de {len(frame)} apuestas. El límite no cambia métricas ni descargas.')
    for start in range(0,len(visible),2):
        cols=st.columns(2)
        for col,(_,row) in zip(cols,visible.iloc[start:start+2].iterrows()):
            with col:
                pick=dict(fecha=row['fecha'],deporte=row['deporte'],partido=row['partido'],seleccion=row['seleccion'],
                    casa=row['casa'],cuota=row['cuota'],probabilidad=row['probabilidad'],referencia=reference(row['referencia']))
                profit='Pendiente' if row['estado']=='Pendiente' else f"${float(row['ganancia_neta']):+,.2f} MXN · {float(row['Beneficio (u)']):+.2f} u"
                render_pick(pick,market='Apuesta realizada',state=row['estado'],allow_register=False,
                    details=[('Monto apostado',f"${float(row['monto']):,.2f} MXN · {float(row['Monto (u)']):.2f} u"),('Beneficio',profit)])

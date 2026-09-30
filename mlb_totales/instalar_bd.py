"""Crear únicamente las dos tablas nuevas, usando los secrets existentes de Streamlit."""
def main():
    import mysql.connector
    import streamlit as st
    from mlb_totales.registro import prepare
    fields={k:st.secrets[k] for k in ('host','port','user','password','database')}
    for key in ('ssl_ca','ssl_verify_cert','ssl_verify_identity'):
        if key in st.secrets:fields[key]=st.secrets[key]
    fields['connection_timeout']=20
    connection=mysql.connector.connect(**fields)
    try:prepare(connection)
    finally:connection.close()
    print('Listo: mlb_totales_predicciones y mlb_totales_resultados preparadas.')


if __name__=='__main__':main()

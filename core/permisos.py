"""Permiso de operación independiente de la presentación; consulta pública por defecto."""
import hmac
import os


def configured_password():
    for name in ('ORACLE_ADMIN_PASSWORD','NFL_ADMIN_PASSWORD','nfl_admin_password'):
        if os.environ.get(name):return os.environ[name]
    try:
        import streamlit as st
        for name in ('ORACLE_ADMIN_PASSWORD','NFL_ADMIN_PASSWORD','nfl_admin_password'):
            if st.secrets.get(name):return str(st.secrets[name])
    except Exception:pass
    return None


def authorized(token):
    expected=configured_password()
    return bool(expected and isinstance(token,str) and hmac.compare_digest(token.encode(),expected.encode()))


def require_admin(token):
    if not authorized(token):raise PermissionError('Se requiere acceso administrativo para esta acción.')


def session_token():
    import streamlit as st
    token=st.session_state.get('_oracle_operator')
    return token if authorized(token) else None


def render_access():
    import streamlit as st
    with st.sidebar.expander('Acceso administrativo'):
        if session_token():
            st.caption('Acceso de operación activo en esta sesión.')
            if st.button('Cerrar acceso',key='oracle_logout'):
                st.session_state.pop('_oracle_operator',None);st.rerun()
        elif not configured_password():
            st.caption('Modo consulta. Configura ORACLE_ADMIN_PASSWORD en Secrets para habilitar actualizaciones.')
        else:
            with st.form('oracle_admin_login'):
                token=st.text_input('Contraseña de operación',type='password',key='_oracle_password_input')
                clicked=st.form_submit_button('Habilitar actualizaciones')
            if clicked:
                if authorized(token):
                    st.session_state['_oracle_operator']=token
                    st.session_state.pop('_oracle_password_input',None)
                    st.rerun()
                else:st.caption('No se pudo habilitar el acceso.')

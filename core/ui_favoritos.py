"""Aplicar/restablecer filtros ocurre antes de crear los widgets del siguiente render."""
from datetime import date
import streamlit as st
from core import preferencias
from core.ui_controles import state_message

SUFFIXES=('period','start','end','season','confidence','market','result','week','provenance','order')


def managed(key,extra):return {suffix:key+'_'+suffix for suffix in SUFFIXES}|(extra or {})


def restore(settings,mapping):
    for name,widget in mapping.items():
        if name not in settings:st.session_state.pop(widget,None);continue
        value=settings[name]
        if name in ('start','end'):
            try:value=date.fromisoformat(value)
            except (TypeError,ValueError):continue
        st.session_state[widget]=value


def render_favorites(key,extra=None):
    mapping=managed(key,extra)
    with st.expander('Favoritos de filtros'):
        st.caption('Favoritos compartidos de esta aplicación, guardados en MySQL. Cárgalos para recuperarlos en otra sesión.')
        if st.button('Cargar favoritos',key=key+'_fav_load'):
            try:st.session_state[key+'_favorites']=preferencias.load(key)
            except Exception:state_message('No se pudieron cargar los favoritos. Puedes seguir usando los filtros.',kind='offline')
        favorites=st.session_state.get(key+'_favorites',{})
        if favorites:
            if st.session_state.get(key+'_fav_choice') not in favorites:st.session_state.pop(key+'_fav_choice',None)
            selected=st.selectbox('Favorito guardado',list(favorites),key=key+'_fav_choice')
            st.button('Aplicar favorito',key=key+'_fav_apply',on_click=restore,args=(favorites[selected],mapping))
            if st.button('Eliminar favorito',key=key+'_fav_delete'):
                try:
                    preferencias.delete(key,selected)
                    st.session_state[key+'_favorites']=preferencias.load(key)
                    st.rerun()
                except Exception:state_message('No se pudo eliminar el favorito.',kind='offline')
        name=st.text_input('Nombre del favorito',max_chars=80,key=key+'_fav_name')
        if st.button('Guardar filtros actuales',key=key+'_fav_save'):
            values={name:st.session_state[widget] for name,widget in mapping.items() if widget in st.session_state}
            try:
                preferencias.save(key,name,values)
                st.session_state[key+'_favorites']=preferencias.load(key)
                st.toast('Filtros guardados.',icon='✅')
            except ValueError as exc:state_message(str(exc),kind='filters')
            except Exception:state_message('No se pudieron guardar los filtros. Reintenta al recuperar MySQL.',kind='offline')
    st.button('Restablecer filtros',key=key+'_reset',on_click=restore,args=({},mapping))

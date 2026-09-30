"""Casa única de referencia para totales MLB, tanto pantalla como Actions."""
BASE_BOOK = 'DraftKings'


def is_base(value):
    return str(value).strip().casefold() == BASE_BOOK.casefold()


def only_base(frame):
    if frame.empty or 'casa_apuestas' not in frame:
        return frame.iloc[0:0].copy()
    result = frame[frame.casa_apuestas.map(is_base)].copy()
    result['casa_apuestas'] = BASE_BOOK
    return result

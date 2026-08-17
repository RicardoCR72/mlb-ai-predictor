import joblib
encoder = joblib.load('encoder_equipos.pkl')
print(list(encoder.classes_))
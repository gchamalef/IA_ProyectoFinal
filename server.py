import threading
import socketserver
import socket
import cv2
import numpy as np
import time

# CONFIGURACION
server_ip = '0.0.0.0'  # Escucha en todas las interfaces
server_port_camera = 8000
server_port_ultrasonic = 8001
server_port_commands = 8002  # Puerto para enviar comandos al carro

image_width = 640
image_height = 480

# Variables globales
ultrasonic_sensor_distance = 1000.0
car_command = "GO"  # Comando por defecto: avanzar

class StreamHandlerUltrasonic(socketserver.BaseRequestHandler):
    def handle(self):
        global ultrasonic_sensor_distance
        try:
            print('Recibiendo datos del sensor ultrasonico...')
            while True:
                data = self.request.recv(1024)
                if not data:
                    break
                try:
                    distance = float(data.decode('utf-8'))
                    ultrasonic_sensor_distance = round(distance, 1)
                except ValueError:
                    pass
        except Exception as e:
            print(f'Error en sensor ultrasonico: {e}')

class StreamHandlerVideocamera(socketserver.StreamRequestHandler):
    def handle(self):
        global ultrasonic_sensor_distance, car_command
        
        # Cargar clasificadores Haar
        stop_cascade = cv2.CascadeClassifier('cascade_xml/stop_sign.xml')
        light_cascade = cv2.CascadeClassifier('cascade_xml/traffic_light.xml')
        
        print('Recibiendo video...')
        stream_bytes = b''
        
        try:
            while True:
                stream_bytes += self.rfile.read(4096)
                
                # Buscar frame JPEG
                first = stream_bytes.find(b'\xff\xd8')
                last = stream_bytes.find(b'\xff\xd9')
                
                if first != -1 and last != -1:
                    jpg = stream_bytes[first:last+2]
                    stream_bytes = stream_bytes[last+2:]
                    
                    image = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                    image_gray = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
                    
                    if image is None:
                        continue
                    
                    # Detectar STOP
                    stops = stop_cascade.detectMultiScale(image_gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
                    for (x, y, w, h) in stops:
                        cv2.rectangle(image, (x, y), (x+w, y+h), (0, 0, 255), 3)
                        cv2.putText(image, 'STOP', (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
                        car_command = "STOP"
                        print('SEÑAL STOP DETECTADA!')
                    
                    # Detectar semáforo
                    lights = light_cascade.detectMultiScale(image_gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
                    for (x, y, w, h) in lights:
                        cv2.rectangle(image, (x, y), (x+w, y+h), (255, 255, 0), 3)
                        cv2.putText(image, 'Traffic Light', (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 0), 2)
                        car_command = "STOP"
                        print('SEMÁFORO DETECTADO!')
                    
                    # Si no detecta nada, comando GO
                    if len(stops) == 0 and len(lights) == 0:
                        car_command = "GO"
                    
                    # Mostrar distancia del sensor
                    if ultrasonic_sensor_distance < 1000:
                        cv2.putText(image, f'Dist: {ultrasonic_sensor_distance}cm', (10, 30), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    
                    cv2.imshow('Carro Robot - Vision', image)
                    
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                        
        except Exception as e:
            print(f'Error en video: {e}')
        finally:
            cv2.destroyAllWindows()

class CommandServer(socketserver.BaseRequestHandler):
    def handle(self):
        global car_command
        print('Servidor de comandos iniciado')
        try:
            while True:
                # Enviar comando al carro
                self.request.sendall(car_command.encode('utf-8'))
                time.sleep(0.1)
        except Exception as e:
            print(f'Error en servidor de comandos: {e}')

def start_server_camera():
    server = socketserver.TCPServer((server_ip, server_port_camera), StreamHandlerVideocamera)
    server.serve_forever()

def start_server_ultrasonic():
    server = socketserver.TCPServer((server_ip, server_port_ultrasonic), StreamHandlerUltrasonic)
    server.serve_forever()

def start_server_commands():
    server = socketserver.TCPServer((server_ip, server_port_commands), CommandServer)
    server.serve_forever()

if __name__ == '__main__':
    print('Iniciando servidor...')
    
    t1 = threading.Thread(target=start_server_ultrasonic, daemon=True)
    t2 = threading.Thread(target=start_server_camera, daemon=True)
    t3 = threading.Thread(target=start_server_commands, daemon=True)
    
    t1.start()
    t2.start()
    t3.start()
    
    print('Servidor listo. Presiona Ctrl+C para detener.')
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print('Servidor detenido.')
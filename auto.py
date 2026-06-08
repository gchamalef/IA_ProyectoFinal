import RPi.GPIO as GPIO
import time
import socket
import struct
import threading
from picamera2 import Picamera2
import cv2
import numpy as np

# PINES GPIO (BCM)
# Motores L298N
ENA = 17
IN1 = 27
IN2 = 22
ENB = 5
IN3 = 6
IN4 = 13

# Sensor ultrasónico
TRIG = 23
ECHO = 24

# CONFIGURACION DE RED
server_ip = '192.168.58.107'  # IP del server
server_port_camera = 8000
server_port_ultrasonic = 8001
server_port_commands = 8002

image_width = 640
image_height = 480

class MotorController:
    def __init__(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        GPIO.setup([IN1, IN2, IN3, IN4], GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup([ENA, ENB], GPIO.OUT)
        
        self.pwm_l = GPIO.PWM(ENA, 50)
        self.pwm_r = GPIO.PWM(ENB, 50)
        self.pwm_l.start(0)
        self.pwm_r.start(0)
        
        GPIO.setup(TRIG, GPIO.OUT)
        GPIO.setup(ECHO, GPIO.IN)
        GPIO.output(TRIG, GPIO.LOW)
        
        print("Motores inicializados")
    
    def avanzar(self, speed=60):
        GPIO.output([IN1, IN3], GPIO.HIGH)
        GPIO.output([IN2, IN4], GPIO.LOW)
        self.pwm_l.ChangeDutyCycle(speed)
        self.pwm_r.ChangeDutyCycle(speed)
    
    def retroceder(self, speed=50):
        GPIO.output([IN1, IN3], GPIO.LOW)
        GPIO.output([IN2, IN4], GPIO.HIGH)
        self.pwm_l.ChangeDutyCycle(speed)
        self.pwm_r.ChangeDutyCycle(speed)
    
    def girar_derecha(self, speed=50):
        GPIO.output(IN1, GPIO.HIGH)
        GPIO.output(IN2, GPIO.LOW)
        GPIO.output(IN3, GPIO.LOW)
        GPIO.output(IN4, GPIO.HIGH)
        self.pwm_l.ChangeDutyCycle(speed)
        self.pwm_r.ChangeDutyCycle(speed)
    
    def detener(self):
        GPIO.output([IN1, IN2, IN3, IN4], GPIO.LOW)
        self.pwm_l.ChangeDutyCycle(0)
        self.pwm_r.ChangeDutyCycle(0)
    
    def medir_distancia(self):
        GPIO.output(TRIG, False)
        time.sleep(0.01)
        GPIO.output(TRIG, True)
        time.sleep(0.00001)
        GPIO.output(TRIG, False)
        
        start_time = time.time()
        timeout = start_time + 0.05
        
        while GPIO.input(ECHO) == 0:
            if time.time() > timeout:
                return 999
        
        inicio = time.time()
        timeout = time.time() + 0.05
        
        while GPIO.input(ECHO) == 1:
            if time.time() > timeout:
                return 999
        
        fin = time.time()
        duracion = fin - inicio
        distancia = (duracion * 34300) / 2
        return distancia
    
    def cleanup(self):
        self.detener()
        self.pwm_l.stop()
        self.pwm_r.stop()
        GPIO.cleanup()

class VideoStreamClient:
    def __init__(self):
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((server_ip, server_port_camera))
            self.connection = self.client_socket.makefile('wb')
            print("Conectado al servidor de video")
        except Exception as e:
            print(f"Error conectando al servidor de video: {e}")
            self.connection = None
    
    def start_stream(self):
        if self.connection is None:
            return
        
        try:
            picam2 = Picamera2()
            config = picam2.create_video_configuration(main={"size": (image_width, image_height)})
            picam2.configure(config)
            picam2.start()
            time.sleep(2)
            
            print("Transmitiendo video...")
            
            while True:
                frame = picam2.capture_array()
                success, encoded_image = cv2.imencode('.jpg', frame)
                if not success:
                    continue
                
                self.connection.write(struct.pack('<L', len(encoded_image)))
                self.connection.flush()
                self.connection.write(encoded_image.tobytes())
                
        except Exception as e:
            print(f"Error en transmisión: {e}")
        finally:
            try:
                if self.connection:
                    self.connection.write(struct.pack('<L', 0))
                    self.connection.close()
                if self.client_socket:
                    self.client_socket.close()
            except:
                pass

class UltrasonicClient:
    def __init__(self):
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((server_ip, server_port_ultrasonic))
            print("Conectado al servidor de ultrasonico")
        except Exception as e:
            print(f"Error conectando al servidor de ultrasonico: {e}")
            self.client_socket = None
    
    def start_stream(self, motor_controller):
        if self.client_socket is None:
            return
        
        try:
            while True:
                distancia = motor_controller.medir_distancia()
                self.client_socket.send(str(distancia).encode('utf-8'))
                time.sleep(0.5)
        except Exception as e:
            print(f"Error en sensor ultrasonico: {e}")
        finally:
            if self.client_socket:
                self.client_socket.close()

class CommandClient:
    def __init__(self):
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((server_ip, server_port_commands))
            print("Conectado al servidor de comandos")
        except Exception as e:
            print(f"Error conectando al servidor de comandos: {e}")
            self.client_socket = None
    
    def get_command(self):
        if self.client_socket is None:
            return "GO"
        
        try:
            data = self.client_socket.recv(1024)
            if data:
                return data.decode('utf-8').strip()
        except:
            pass
        
        return "GO"

def modo_autonomo(motor_controller, command_client):
    print("Modo autónomo iniciado")
    
    try:
        while True:
            distancia = motor_controller.medir_distancia()
            comando = command_client.get_command()
            
            print(f"Distancia: {distancia:.1f}cm | Comando: {comando}")
            
            # Si el servidor detectó STOP o semáforo
            if comando == "STOP":
                print("PARADA POR SEÑAL DE TRANSITO")
                motor_controller.detener()
                time.sleep(2)
                continue
            
            # Evitación de obstáculos local
            if distancia > 20:
                motor_controller.avanzar(60)
            else:
                print("Obstaculo detectado, evadiendo...")
                motor_controller.detener()
                time.sleep(0.3)
                motor_controller.retroceder(50)
                time.sleep(0.5)
                motor_controller.detener()
                time.sleep(0.2)
                motor_controller.girar_derecha(50)
                time.sleep(0.5)
                motor_controller.detener()
                time.sleep(0.2)
            
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("Detenido por usuario")
    finally:
        motor_controller.detener()

def main():
    print("Iniciando carro robot con vision computacional")
    
    motor_controller = MotorController()
    
    # Iniciar clientes de transmisión
    video_client = VideoStreamClient()
    ultrasonic_client = UltrasonicClient()
    command_client = CommandClient()
    
    # Hilos para transmisión
    thread_video = threading.Thread(target=video_client.start_stream, daemon=True)
    thread_ultrasonic = threading.Thread(target=ultrasonic_client.start_stream, args=(motor_controller,), daemon=True)
    
    thread_video.start()
    thread_ultrasonic.start()
    
    # Modo autónomo principal
    modo_autonomo(motor_controller, command_client)
    
    motor_controller.cleanup()

if __name__ == '__main__':
    main()
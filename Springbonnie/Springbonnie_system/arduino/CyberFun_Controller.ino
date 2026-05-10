/*
================================================================================
  CYBER FUN ENDOSKELETON - Controlador Arduino Mega 2560
  Sistema de controle de hardware completo: Servos, Motores, LEDs, Sensores, IMU
================================================================================
  Hardware:
    - Arduino Mega 2560
    - 16x Servos (PWM via pinos 2-13, 44-46)
    - 2x Motor DC (L298N Dual H-Bridge)
    - 60x NeoPixel RGB LEDs (olhos, boca, corpo)
    - 4x HC-SR04 Ultrassonicos (frente, trás, esquerda, direita)
    - 1x MPU-6050 IMU (giroscópio + acelerômetro)
    - 1x DS18B20 Temperatura
    - 1x PIR Sensor (detecção de presença)
    - 1x Botão de Emergência (parada imediata)
    - Buzzer ativo (feedback sonoro)
    - Comunicação Serial com Raspberry Pi 4 @ 115200 baud
================================================================================
  Protocolo Serial:
    Incoming: #<CMD><PARAMS>\n
    Outgoing: @<TYPE><DATA>\n
================================================================================
*/

#include <Servo.h>
#include <Wire.h>
#include <Adafruit_NeoPixel.h>
#include <NewPing.h>

// ==================== PINOS ====================
// Servos faciais
#define PIN_SERVO_JAW         2
#define PIN_SERVO_LEFT_EYE    3
#define PIN_SERVO_RIGHT_EYE   4
#define PIN_SERVO_EYE_X       5
#define PIN_SERVO_EYE_Y       6
#define PIN_SERVO_LEFT_EAR    7
#define PIN_SERVO_RIGHT_EAR   8
// Servos de corpo
#define PIN_SERVO_HEAD_PAN    9
#define PIN_SERVO_HEAD_TILT  10
#define PIN_SERVO_LEFT_SHLD  11
#define PIN_SERVO_RIGHT_SHLD 12
#define PIN_SERVO_LEFT_ELBOW 13
#define PIN_SERVO_RIGHT_ELBW 44
#define PIN_SERVO_LEFT_WRIST 45
#define PIN_SERVO_RIGHT_WRST 46
#define PIN_SERVO_TORSO      47

// Motores DC (L298N)
#define PIN_MOTOR_L_PWM  4
#define PIN_MOTOR_L_IN1  22
#define PIN_MOTOR_L_IN2  23
#define PIN_MOTOR_R_PWM  5
#define PIN_MOTOR_R_IN1  24
#define PIN_MOTOR_R_IN2  25

// NeoPixel
#define PIN_NEOPIXEL     26
#define NUM_PIXELS       60

// Sensores ultrassônicos
#define PIN_US_FRONT_TRIG  27
#define PIN_US_FRONT_ECHO  28
#define PIN_US_BACK_TRIG   29
#define PIN_US_BACK_ECHO   30
#define PIN_US_LEFT_TRIG   31
#define PIN_US_LEFT_ECHO   32
#define PIN_US_RIGHT_TRIG  33
#define PIN_US_RIGHT_ECHO  34

// Sensores digitais
#define PIN_PIR           35
#define PIN_ESTOP         36   // Botão de emergência (pull-up)
#define PIN_BUZZER        37

// I2C (MPU-6050)
#define MPU_ADDR         0x68

// Constantes
#define MAX_SERVOS        16
#define MAX_DISTANCE_CM   300
#define HEARTBEAT_TIMEOUT 3000  // ms sem heartbeat = emergência
#define SERIAL_BAUD       115200
#define UPDATE_RATE_HZ    60

// ==================== OBJETOS ====================
Servo servos[MAX_SERVOS];
Adafruit_NeoPixel strip(NUM_PIXELS, PIN_NEOPIXEL, NEO_GRB + NEO_KHZ800);
NewPing sonar_front(PIN_US_FRONT_TRIG, PIN_US_FRONT_ECHO, MAX_DISTANCE_CM);
NewPing sonar_back(PIN_US_BACK_TRIG,   PIN_US_BACK_ECHO,  MAX_DISTANCE_CM);
NewPing sonar_left(PIN_US_LEFT_TRIG,   PIN_US_LEFT_ECHO,  MAX_DISTANCE_CM);
NewPing sonar_right(PIN_US_RIGHT_TRIG, PIN_US_RIGHT_ECHO, MAX_DISTANCE_CM);

// ==================== ESTADO GLOBAL ====================
struct SystemState {
  bool emergency_stop = false;
  bool motors_enabled = true;
  bool servos_enabled = true;
  bool lights_enabled = true;
  unsigned long last_heartbeat = 0;
  float battery_voltage = 12.0;
  float temperature_c = 25.0;
  bool pir_detected = false;
  int servo_positions[MAX_SERVOS];
  int motor_left_speed = 0;
  int motor_right_speed = 0;
  // IMU
  float acc_x = 0, acc_y = 0, acc_z = 0;
  float gyr_x = 0, gyr_y = 0, gyr_z = 0;
} state;

// Configurações de servo (min_pulse, max_pulse, neutral)
const int SERVO_MIN[MAX_SERVOS] = {
  700,  500,  500,  500,  500,  700,  700,  // Faciais (0-6)
  500,  600,  500,  500,  600,  600,  800,  // Corpo (7-13)
  800,  500                                  // Resto (14-15)
};
const int SERVO_MAX[MAX_SERVOS] = {
  2200, 2500, 2500, 2500, 2500, 2200, 2200,
  2500, 2300, 2500, 2500, 2300, 2300, 2100,
  2100, 2500
};
const int SERVO_NEUTRAL[MAX_SERVOS] = {
  700,  1500, 1500, 1500, 1500, 1500, 1500,
  1500, 1500, 1500, 1500, 1500, 1500, 1500,
  1500, 1500
};

// Nomes dos servos (para debug)
const char* SERVO_NAMES[MAX_SERVOS] = {
  "Jaw", "LEyelid", "REyelid", "EyeX", "EyeY", "LEar", "REar",
  "HeadPan", "HeadTilt", "LShld", "RShld", "LElbow", "RElbow",
  "LWrist", "RWrist", "Torso"
};

// Buffer serial
String serial_buffer = "";
bool new_data = false;

// Timers
unsigned long last_sensor_read = 0;
unsigned long last_imu_read = 0;
unsigned long last_battery_read = 0;
unsigned long last_status_send = 0;

// ==================== SETUP ====================
void setup() {
  Serial.begin(SERIAL_BAUD);
  Serial.println(F("@BOOT CyberFun v3.0 Mega2560 iniciando..."));

  // Inicializar servos
  int servo_pins[MAX_SERVOS] = {
    PIN_SERVO_JAW, PIN_SERVO_LEFT_EYE, PIN_SERVO_RIGHT_EYE,
    PIN_SERVO_EYE_X, PIN_SERVO_EYE_Y, PIN_SERVO_LEFT_EAR, PIN_SERVO_RIGHT_EAR,
    PIN_SERVO_HEAD_PAN, PIN_SERVO_HEAD_TILT,
    PIN_SERVO_LEFT_SHLD, PIN_SERVO_RIGHT_SHLD,
    PIN_SERVO_LEFT_ELBOW, PIN_SERVO_RIGHT_ELBW,
    PIN_SERVO_LEFT_WRIST, PIN_SERVO_RIGHT_WRST,
    PIN_SERVO_TORSO
  };

  for (int i = 0; i < MAX_SERVOS; i++) {
    servos[i].attach(servo_pins[i], SERVO_MIN[i], SERVO_MAX[i]);
    state.servo_positions[i] = SERVO_NEUTRAL[i];
    servos[i].writeMicroseconds(SERVO_NEUTRAL[i]);
    delay(20);
  }
  Serial.println(F("@OK Servos inicializados"));

  // Inicializar motores
  pinMode(PIN_MOTOR_L_PWM, OUTPUT);
  pinMode(PIN_MOTOR_L_IN1, OUTPUT);
  pinMode(PIN_MOTOR_L_IN2, OUTPUT);
  pinMode(PIN_MOTOR_R_PWM, OUTPUT);
  pinMode(PIN_MOTOR_R_IN1, OUTPUT);
  pinMode(PIN_MOTOR_R_IN2, OUTPUT);
  stopMotors();
  Serial.println(F("@OK Motores inicializados"));

  // NeoPixel
  strip.begin();
  strip.setBrightness(80);
  boot_animation();
  Serial.println(F("@OK NeoPixel inicializado"));

  // Sensores
  pinMode(PIN_PIR, INPUT);
  pinMode(PIN_ESTOP, INPUT_PULLUP);
  pinMode(PIN_BUZZER, OUTPUT);

  // IMU MPU-6050
  Wire.begin();
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x6B);  // PWR_MGMT_1
  Wire.write(0);     // Wake up
  Wire.endTransmission(true);
  Serial.println(F("@OK IMU inicializado"));

  // Heartbeat inicial
  state.last_heartbeat = millis();

  beep(2, 100);  // 2 beeps = pronto
  Serial.println(F("@READY Sistema pronto!"));
}

// ==================== LOOP PRINCIPAL ====================
void loop() {
  unsigned long now = millis();

  // 1. Checar botão de emergência (máxima prioridade)
  if (digitalRead(PIN_ESTOP) == LOW) {
    triggerEmergencyStop("BUTTON");
  }

  // 2. Checar heartbeat timeout
  if (!state.emergency_stop && (now - state.last_heartbeat > HEARTBEAT_TIMEOUT)) {
    triggerEmergencyStop("HEARTBEAT_TIMEOUT");
  }

  // 3. Ler comandos seriais
  readSerial();

  // 4. Processar comando se disponível
  if (new_data) {
    processCommand(serial_buffer);
    serial_buffer = "";
    new_data = false;
  }

  // 5. Leitura periódica de sensores (50ms = 20Hz)
  if (now - last_sensor_read >= 50) {
    readSensors();
    last_sensor_read = now;
  }

  // 6. Leitura IMU (16ms = 60Hz)
  if (now - last_imu_read >= 16) {
    readIMU();
    last_imu_read = now;
  }

  // 7. Bateria (1s)
  if (now - last_battery_read >= 1000) {
    readBattery();
    last_battery_read = now;
  }

  // 8. Enviar status periódico (500ms)
  if (now - last_status_send >= 500) {
    sendStatus();
    last_status_send = now;
  }
}

// ==================== LEITURA SERIAL ====================
void readSerial() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      new_data = true;
      break;
    }
    if (c != '\r') {
      serial_buffer += c;
    }
  }
}

// ==================== PROCESSAMENTO DE COMANDOS ====================
void processCommand(String cmd) {
  cmd.trim();
  if (cmd.length() < 2) return;

  char type = cmd.charAt(0);
  if (type != '#') return;

  String payload = cmd.substring(1);

  // ---- SERVO ----
  if (payload.startsWith("S")) {
    // #S<id>P<pulse>   ex: #S0P1200
    int sep = payload.indexOf('P', 1);
    if (sep > 0) {
      int id    = payload.substring(1, sep).toInt();
      int pulse = payload.substring(sep + 1).toInt();
      setServoPulse(id, pulse);
    }
  }
  // ---- SERVO MULTI ----
  else if (payload.startsWith("M")) {
    // #M<s0>:<p0>,<s1>:<p1>,...   ex: #M0:1200,1:1500,3:1800
    String data = payload.substring(1);
    int start = 0;
    while (start < data.length()) {
      int comma = data.indexOf(',', start);
      String token = (comma >= 0) ? data.substring(start, comma) : data.substring(start);
      int colon = token.indexOf(':');
      if (colon >= 0) {
        int id    = token.substring(0, colon).toInt();
        int pulse = token.substring(colon + 1).toInt();
        setServoPulse(id, pulse);
      }
      if (comma < 0) break;
      start = comma + 1;
    }
  }
  // ---- MOTOR LEFT ----
  else if (payload.startsWith("ML")) {
    int speed = payload.substring(2).toInt();
    setMotorLeft(speed);
  }
  // ---- MOTOR RIGHT ----
  else if (payload.startsWith("MR")) {
    int speed = payload.substring(2).toInt();
    setMotorRight(speed);
  }
  // ---- MOTOR AMBOS ----
  else if (payload.startsWith("MB")) {
    // #MB<left>,<right>
    int comma = payload.indexOf(',', 2);
    if (comma >= 0) {
      int l = payload.substring(2, comma).toInt();
      int r = payload.substring(comma + 1).toInt();
      setMotorLeft(l);
      setMotorRight(r);
    }
  }
  // ---- LED RGB ----
  else if (payload.startsWith("L")) {
    // #L<start>:<end>:<R>:<G>:<B>  ex: #L0:10:255:0:0
    String data = payload.substring(1);
    int c1 = data.indexOf(':');
    int c2 = data.indexOf(':', c1+1);
    int c3 = data.indexOf(':', c2+1);
    int c4 = data.indexOf(':', c3+1);
    if (c4 >= 0) {
      int start = data.substring(0, c1).toInt();
      int end   = data.substring(c1+1, c2).toInt();
      int r     = data.substring(c2+1, c3).toInt();
      int g     = data.substring(c3+1, c4).toInt();
      int b     = data.substring(c4+1).toInt();
      setLEDRange(start, end, r, g, b);
    }
  }
  // ---- LED PIXEL INDIVIDUAL ----
  else if (payload.startsWith("P")) {
    // #P<pixel>:<R>:<G>:<B>
    String data = payload.substring(1);
    int c1 = data.indexOf(':');
    int c2 = data.indexOf(':', c1+1);
    int c3 = data.indexOf(':', c2+1);
    if (c3 >= 0) {
      int px = data.substring(0, c1).toInt();
      int r  = data.substring(c1+1, c2).toInt();
      int g  = data.substring(c2+1, c3).toInt();
      int b  = data.substring(c3+1).toInt();
      strip.setPixelColor(px, strip.Color(r, g, b));
      strip.show();
    }
  }
  // ---- BRILHO LED ----
  else if (payload.startsWith("B")) {
    int brightness = payload.substring(1).toInt();
    strip.setBrightness(constrain(brightness, 0, 255));
    strip.show();
  }
  // ---- EFEITO LED ----
  else if (payload.startsWith("FX")) {
    // #FX<effect>:<param>
    String data = payload.substring(2);
    int col = data.indexOf(':');
    String effect = (col >= 0) ? data.substring(0, col) : data;
    int param = (col >= 0) ? data.substring(col+1).toInt() : 0;
    runLEDEffect(effect, param);
  }
  // ---- HOME TODOS SERVOS ----
  else if (payload == "HOME") {
    homeAllServos();
    Serial.println(F("@OK HOME completo"));
  }
  // ---- EMERGÊNCIA ----
  else if (payload == "ESTOP") {
    triggerEmergencyStop("COMMAND");
  }
  // ---- RESETAR EMERGÊNCIA ----
  else if (payload == "RESET") {
    releaseEmergencyStop();
  }
  // ---- HEARTBEAT ----
  else if (payload == "HB") {
    state.last_heartbeat = millis();
    Serial.println(F("@HB"));
  }
  // ---- BEEP ----
  else if (payload.startsWith("BEEP")) {
    String data = payload.substring(4);
    int comma = data.indexOf(',');
    int count = (comma >= 0) ? data.substring(0, comma).toInt() : 1;
    int ms    = (comma >= 0) ? data.substring(comma+1).toInt() : 100;
    beep(count, ms);
  }
  // ---- HABILITAR/DESABILITAR ----
  else if (payload.startsWith("EN")) {
    String data = payload.substring(2);
    if (data == "MOTORS1") state.motors_enabled = true;
    else if (data == "MOTORS0") { state.motors_enabled = false; stopMotors(); }
    else if (data == "SERVO1") state.servos_enabled = true;
    else if (data == "SERVO0") state.servos_enabled = false;
    else if (data == "LIGHTS1") state.lights_enabled = true;
    else if (data == "LIGHTS0") { state.lights_enabled = false; strip.clear(); strip.show(); }
    Serial.print(F("@OK EN ")); Serial.println(data);
  }
  // ---- STATUS ----
  else if (payload == "STATUS") {
    sendStatus();
  }
  // ---- VERSÃO ----
  else if (payload == "VER") {
    Serial.println(F("@VER CyberFun-Arduino v3.0 Mega2560"));
  }
  // ---- PING ----
  else if (payload == "PING") {
    Serial.println(F("@PONG"));
  }
  else {
    Serial.print(F("@ERR Comando desconhecido: "));
    Serial.println(payload);
  }
}

// ==================== CONTROLE DE SERVOS ====================
void setServoPulse(int id, int pulse) {
  if (state.emergency_stop || !state.servos_enabled) return;
  if (id < 0 || id >= MAX_SERVOS) {
    Serial.print(F("@ERR Servo ID invalido: ")); Serial.println(id);
    return;
  }
  pulse = constrain(pulse, SERVO_MIN[id], SERVO_MAX[id]);
  state.servo_positions[id] = pulse;
  servos[id].writeMicroseconds(pulse);

  Serial.print(F("@S")); Serial.print(id);
  Serial.print(F("P")); Serial.println(pulse);
}

void homeAllServos() {
  for (int i = 0; i < MAX_SERVOS; i++) {
    setServoPulse(i, SERVO_NEUTRAL[i]);
    delay(10);
  }
}

// ==================== CONTROLE DE MOTORES ====================
void setMotorLeft(int speed) {
  if (state.emergency_stop || !state.motors_enabled) { stopMotors(); return; }
  speed = constrain(speed, -255, 255);
  state.motor_left_speed = speed;
  if (speed > 0) {
    digitalWrite(PIN_MOTOR_L_IN1, HIGH);
    digitalWrite(PIN_MOTOR_L_IN2, LOW);
    analogWrite(PIN_MOTOR_L_PWM, speed);
  } else if (speed < 0) {
    digitalWrite(PIN_MOTOR_L_IN1, LOW);
    digitalWrite(PIN_MOTOR_L_IN2, HIGH);
    analogWrite(PIN_MOTOR_L_PWM, -speed);
  } else {
    digitalWrite(PIN_MOTOR_L_IN1, LOW);
    digitalWrite(PIN_MOTOR_L_IN2, LOW);
    analogWrite(PIN_MOTOR_L_PWM, 0);
  }
}

void setMotorRight(int speed) {
  if (state.emergency_stop || !state.motors_enabled) { stopMotors(); return; }
  speed = constrain(speed, -255, 255);
  state.motor_right_speed = speed;
  if (speed > 0) {
    digitalWrite(PIN_MOTOR_R_IN1, HIGH);
    digitalWrite(PIN_MOTOR_R_IN2, LOW);
    analogWrite(PIN_MOTOR_R_PWM, speed);
  } else if (speed < 0) {
    digitalWrite(PIN_MOTOR_R_IN1, LOW);
    digitalWrite(PIN_MOTOR_R_IN2, HIGH);
    analogWrite(PIN_MOTOR_R_PWM, -speed);
  } else {
    digitalWrite(PIN_MOTOR_R_IN1, LOW);
    digitalWrite(PIN_MOTOR_R_IN2, LOW);
    analogWrite(PIN_MOTOR_R_PWM, 0);
  }
}

void stopMotors() {
  state.motor_left_speed = 0;
  state.motor_right_speed = 0;
  digitalWrite(PIN_MOTOR_L_IN1, LOW);
  digitalWrite(PIN_MOTOR_L_IN2, LOW);
  analogWrite(PIN_MOTOR_L_PWM, 0);
  digitalWrite(PIN_MOTOR_R_IN1, LOW);
  digitalWrite(PIN_MOTOR_R_IN2, LOW);
  analogWrite(PIN_MOTOR_R_PWM, 0);
}

// ==================== CONTROLE DE LEDs ====================
void setLEDRange(int start, int end, int r, int g, int b) {
  if (!state.lights_enabled) return;
  start = constrain(start, 0, NUM_PIXELS - 1);
  end   = constrain(end,   0, NUM_PIXELS - 1);
  for (int i = start; i <= end; i++) {
    strip.setPixelColor(i, strip.Color(r, g, b));
  }
  strip.show();
}

void runLEDEffect(String effect, int param) {
  if (effect == "PULSE") {
    // Pulsar entre min e max brilho
    for (int b = 0; b <= 255; b += 5) {
      strip.setBrightness(b);
      strip.show();
      delay(10);
    }
  } else if (effect == "RAINBOW") {
    for (int j = 0; j < 256; j++) {
      for (int i = 0; i < NUM_PIXELS; i++) {
        strip.setPixelColor(i, Wheel((i * 256 / NUM_PIXELS + j) & 255));
      }
      strip.show();
      delay(5);
    }
  } else if (effect == "WIPE") {
    uint32_t color = strip.Color(0, 100, 255);
    for (int i = 0; i < NUM_PIXELS; i++) {
      strip.setPixelColor(i, color);
      strip.show();
      delay(param > 0 ? param : 20);
    }
  } else if (effect == "CLEAR") {
    strip.clear();
    strip.show();
  } else if (effect == "ALERT") {
    // Vermelho piscando - alerta
    for (int i = 0; i < 5; i++) {
      setLEDRange(0, NUM_PIXELS - 1, 255, 0, 0);
      delay(150);
      strip.clear(); strip.show();
      delay(150);
    }
  } else if (effect == "SUCCESS") {
    // Verde piscando - sucesso
    setLEDRange(0, NUM_PIXELS - 1, 0, 255, 0);
    delay(500);
    strip.clear(); strip.show();
  }
}

// ==================== SENSORES ====================
void readSensors() {
  // PIR
  bool pir = digitalRead(PIN_PIR);
  if (pir != state.pir_detected) {
    state.pir_detected = pir;
    Serial.print(F("@PIR ")); Serial.println(pir ? "1" : "0");
  }

  // Ultrassônicos (em rodízio para não causar interferência)
  static int sonar_turn = 0;
  unsigned int dist = 0;
  switch (sonar_turn) {
    case 0: dist = sonar_front.ping_cm(); Serial.print(F("@UF ")); break;
    case 1: dist = sonar_back.ping_cm();  Serial.print(F("@UB ")); break;
    case 2: dist = sonar_left.ping_cm();  Serial.print(F("@UL ")); break;
    case 3: dist = sonar_right.ping_cm(); Serial.print(F("@UR ")); break;
  }
  Serial.println(dist == 0 ? MAX_DISTANCE_CM : dist);
  sonar_turn = (sonar_turn + 1) % 4;
}

void readIMU() {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);
  Wire.endTransmission(false);
  Wire.requestFrom(MPU_ADDR, 14, true);

  int16_t AcX = Wire.read() << 8 | Wire.read();
  int16_t AcY = Wire.read() << 8 | Wire.read();
  int16_t AcZ = Wire.read() << 8 | Wire.read();
  Wire.read(); Wire.read(); // Temperatura
  int16_t GyX = Wire.read() << 8 | Wire.read();
  int16_t GyY = Wire.read() << 8 | Wire.read();
  int16_t GyZ = Wire.read() << 8 | Wire.read();

  state.acc_x = AcX / 16384.0;
  state.acc_y = AcY / 16384.0;
  state.acc_z = AcZ / 16384.0;
  state.gyr_x = GyX / 131.0;
  state.gyr_y = GyY / 131.0;
  state.gyr_z = GyZ / 131.0;

  // Publicar IMU a cada 200ms
  static unsigned long last_imu_pub = 0;
  if (millis() - last_imu_pub >= 200) {
    Serial.print(F("@IMU "));
    Serial.print(state.acc_x, 2); Serial.print(F(","));
    Serial.print(state.acc_y, 2); Serial.print(F(","));
    Serial.print(state.acc_z, 2); Serial.print(F(","));
    Serial.print(state.gyr_x, 1); Serial.print(F(","));
    Serial.print(state.gyr_y, 1); Serial.print(F(","));
    Serial.println(state.gyr_z, 1);
    last_imu_pub = millis();
  }
}

void readBattery() {
  // Leitura analógica do divisor de tensão
  int raw = analogRead(A0);
  state.battery_voltage = (raw / 1023.0) * 5.0 * 3.0; // Fator do divisor
  Serial.print(F("@BAT ")); Serial.println(state.battery_voltage, 2);
}

// ==================== EMERGÊNCIA ====================
void triggerEmergencyStop(const char* reason) {
  if (state.emergency_stop) return;
  state.emergency_stop = true;
  stopMotors();
  homeAllServos();
  runLEDEffect("ALERT", 0);
  beep(5, 200);

  Serial.print(F("@ESTOP "));
  Serial.println(reason);
}

void releaseEmergencyStop() {
  state.emergency_stop = false;
  state.last_heartbeat = millis();
  state.motors_enabled = true;
  state.servos_enabled = true;
  runLEDEffect("SUCCESS", 0);
  beep(2, 50);
  Serial.println(F("@RESET OK"));
}

// ==================== STATUS ====================
void sendStatus() {
  Serial.print(F("@STATUS "));
  Serial.print(state.emergency_stop ? "ESTOP" : "OK");
  Serial.print(F(" BAT:")); Serial.print(state.battery_voltage, 1);
  Serial.print(F(" TEMP:")); Serial.print(state.temperature_c, 1);
  Serial.print(F(" PIR:")); Serial.print(state.pir_detected ? "1" : "0");
  Serial.print(F(" ML:")); Serial.print(state.motor_left_speed);
  Serial.print(F(" MR:")); Serial.println(state.motor_right_speed);
}

// ==================== UTILITÁRIOS ====================
void beep(int times, int duration_ms) {
  for (int i = 0; i < times; i++) {
    digitalWrite(PIN_BUZZER, HIGH);
    delay(duration_ms);
    digitalWrite(PIN_BUZZER, LOW);
    if (i < times - 1) delay(duration_ms / 2);
  }
}

void boot_animation() {
  // Animação de boot nos olhos (NeoPixel 0-5 = olho esq, 6-11 = olho dir)
  for (int i = 0; i < NUM_PIXELS; i++) {
    strip.setPixelColor(i, strip.Color(0, 0, 50));
    strip.show();
    delay(10);
  }
  delay(200);
  for (int b = 50; b <= 255; b += 5) {
    strip.setBrightness(b);
    strip.show();
    delay(5);
  }
  strip.setBrightness(80);
  // Olhos azuis (padrão CyberFun)
  setLEDRange(0, 5,  0, 100, 255);   // Olho esquerdo
  setLEDRange(6, 11, 0, 100, 255);   // Olho direito
}

uint32_t Wheel(byte pos) {
  pos = 255 - pos;
  if (pos < 85)  return strip.Color(255 - pos * 3, 0, pos * 3);
  if (pos < 170) { pos -= 85; return strip.Color(0, pos * 3, 255 - pos * 3); }
  pos -= 170;    return strip.Color(pos * 3, 255 - pos * 3, 0);
}

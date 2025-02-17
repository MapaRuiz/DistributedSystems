import java.io.*;
import java.net.*;

class Cliente {
    public static void main(String[] args) {
        System.setProperty("java.net.preferIPv4Stack", "true");
        try (Socket socket = new Socket("10.147.19.244", 5000);

                DataOutputStream out = new DataOutputStream(socket.getOutputStream());
                DataInputStream in = new DataInputStream(socket.getInputStream())) {
            System.out.println("Conectado al servidor con ip 10.147.19.244");
            double a = 123456789.0, b = 987654321.0;
            out.writeDouble(a);
            out.writeDouble(b);

            double resultado = in.readDouble();
            System.out.println("Hipotenusa calculada: " + resultado);
        } catch (IOException e) {
            e.printStackTrace();
        }
    }
}
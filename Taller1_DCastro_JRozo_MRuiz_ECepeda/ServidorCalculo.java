import java.io.*;
import java.net.*;

class ServidorCalculo {
    public static void main(String[] args) {
        try (ServerSocket serverSocket = new ServerSocket(5000, 50, InetAddress.getByName("10.147.19.244"))) {
            System.out.println("Servidor de cálculo esperando cliente...");
            Socket clienteSocket = serverSocket.accept();
            System.out.println("Cliente conectado.");
            
            DataInputStream in = new DataInputStream(clienteSocket.getInputStream());
            DataOutputStream out = new DataOutputStream(clienteSocket.getOutputStream());
            
            double a = in.readDouble();
            double b = in.readDouble();
            
            // Se envían valores al servidor de operación
            double a2 = enviarOperacion(a, "10.147.19.224", 5001); // Servidor de Operación
            double b2 = enviarOperacion(b, "10.147.19.225", 5001); // Servidor de Operación
            
            double hipotenusa = Math.sqrt(a2 + b2);
            System.out.println("Enviando resultado: "+ hipotenusa);
            out.writeDouble(hipotenusa);
        } catch (IOException e) {
            e.printStackTrace();
        }
    }
    
    private static double enviarOperacion(double valor, String ip, int puerto) {
        try (Socket socket = new Socket(ip, puerto);
             DataOutputStream out = new DataOutputStream(socket.getOutputStream());
             DataInputStream in = new DataInputStream(socket.getInputStream())) {
            
            out.writeDouble(valor);
            System.out.println("Servidor en " + ip + " respondió correctamente.");
        
            double resultado = in.readDouble(); // Guardamos el resultado en una variable
            System.out.println("Resultado calculado remotamente: " + resultado);
        
            return resultado; // Retornamos la misma variable
        } catch (IOException e) {
            System.out.println("Servidor en " + ip + " no responde. Calculando localmente.");
            System.out.println("Resultado calculado localmente: "+ (valor * valor));
            return valor * valor;
        }
    }
}

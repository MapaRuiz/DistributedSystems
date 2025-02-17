import java.io.*;
import java.net.*;

class ServidorOperacion {
    public static void main(String[] args) {
        try (ServerSocket serverSocket = new ServerSocket(5001, 50, InetAddress.getByName("10.147.19.5"))) {
            System.out.println("Servidor de operación escuchando en puerto 5001");
            while (true) {
                Socket socket = serverSocket.accept();
                System.out.println("Servidor de Cálculo conectado desde: " + socket.getInetAddress().getHostAddress());
                new Thread(new ManejadorOperacion(socket)).start();
                return;
            }
        } catch (IOException e) {
            e.printStackTrace();
        }
    }
}

class ManejadorOperacion implements Runnable {
    private Socket socket;

    public ManejadorOperacion(Socket socket) {
        this.socket = socket;
    }

    @Override
    public void run() {
        try (DataInputStream in = new DataInputStream(socket.getInputStream());
             DataOutputStream out = new DataOutputStream(socket.getOutputStream())) {

            double valor = in.readDouble();
            System.out.println(" Recibí el valor: " + valor);

            double resultado = valor * valor;
            System.out.println("Enviando resultado: " + resultado);

            out.writeDouble(resultado);
        } catch (IOException e) {
            e.printStackTrace();
        }
    }
}

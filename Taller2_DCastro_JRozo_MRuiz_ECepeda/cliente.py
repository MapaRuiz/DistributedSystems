import grpc
import calc_pb2
import calc_pb2_grpc

def run():
    server_address = '10.43.96.50:5000'  # Dirección del servidor de cálculo
    print(f"Conectando al servidor de cálculo en {server_address}...")

    try:
        with grpc.insecure_channel(server_address) as channel:
            stub = calc_pb2_grpc.CalculationServiceStub(channel)

            # Valores de ejemplo
            a = 12
            b = 13
            print(f"Enviando solicitud con a={a}, b={b}...")

            response = stub.Calculate(calc_pb2.CalculationRequest(a=a, b=b))
            print(f"Hipotenusa calculada: {response.hypotenuse}")

    except grpc.RpcError as e:
        print(f"Error en la conexión con el servidor: {e}")

if __name__ == "__main__":  
    run()  

from concurrent import futures
import grpc
import calc_pb2
import calc_pb2_grpc

class OperationService(calc_pb2_grpc.OperationServiceServicer):
    def Square(self, request, context):
        value = request.value
        result = value * value
        print(f"[Server1] Received value: {value}, returning square: {result}")
        return calc_pb2.OperationReply(result=result)

def serve():
    try:
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        calc_pb2_grpc.add_OperationServiceServicer_to_server(OperationService(), server)
        server.add_insecure_port('10.43.96.60:50051')  # Cambia el puerto si es necesario
        server.start()
        print("Operation Server 1 started on port 50051")
        server.wait_for_termination()  
    except Exception as e:
        print(f"ERROR ABRIENDO EL PUERTO 5001: {e}")

if __name__ == "__main__":  
    serve()  
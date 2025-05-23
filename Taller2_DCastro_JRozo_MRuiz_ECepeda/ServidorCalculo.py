from concurrent import futures
import math
import grpc
import calc_pb2
import calc_pb2_grpc

class CalculationService(calc_pb2_grpc.CalculationServiceServicer):
    def Calculate(self, request, context):
        a = request.a
        b = request.b

        # Try to contact Operation Server 1 (for a)
        try:
            with grpc.insecure_channel('localhost:50051') as channel:
                stub = calc_pb2_grpc.OperationServiceStub(channel)
                response_a = stub.Square(calc_pb2.OperationRequest(value=a))
                a_squared = response_a.result
                print(f"Operation Server 1 squared {a}: {a_squared}")
        except Exception as e:
            print(f"Operation Server 1 failed: {e}")
            a_squared = a * a

        # Try to contact Operation Server 2 (for b)
        try:
            with grpc.insecure_channel('localhost:50052') as channel:
                stub = calc_pb2_grpc.OperationServiceStub(channel)
                response_b = stub.Square(calc_pb2.OperationRequest(value=b))
                b_squared = response_b.result
                print(f"Operation Server 2 squared {b}: {b_squared}")
        except Exception as e:
            print(f"Operation Server 2 failed: {e}")
            b_squared = b * b

        hypotenuse = math.sqrt(a_squared + b_squared)
        print(f"Calculated hypotenuse: {hypotenuse}")
        return calc_pb2.CalculationReply(hypotenuse=hypotenuse)

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    calc_pb2_grpc.add_CalculationServiceServicer_to_server(CalculationService(), server)
    server.add_insecure_port('[::]:5000')  # The calculation server listens on port 5000
    server.start()
    print("Calculation Server started on port 5000")
    server.wait_for_termination()

if _name_ == '_main_':
    serve()
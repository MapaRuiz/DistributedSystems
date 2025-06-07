#!/bin/bash


# Lanzar 5 facultades en diferentes puertos, en segundo plano
for i in {1..5}; do
  port=$((5999 + i))
  echo " Iniciando facultad $i en puerto $port..."
  python3 ~/Documents/ProyectoMetricas/faculty.py --faculty-id $i --faculty-name Facultad_$i --port $port > "facultad_${i}.log" 2>&1 &
  s
done

#


# Enviar solicitudes: 5 programas por facultad, cada uno solicita 10 aulas y 4 labs
echo " Enviando solicitudes de programas académicos..."
for i in {1..5}; do
  for j in {1..5}; do
    aulas=10
    labs=4
    port=$((5999 + i))
    echo "➡️  Facultad $i | Programa $j solicita $aulas aulas y $labs labs (Puerto $port)"
    python3 ~/Documents/ProyectoMetricas/academic_program.py "Prog_${i}_${j}" "2025-2" $aulas $labs "tcp://localhost:$port" $i &
   
  done
done

# Esperar a que todos los programas terminen
wait

echo "✅ Simulación completada."

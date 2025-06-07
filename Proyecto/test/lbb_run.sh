#!/bin/bash

# Lanzar 5 facultades LBB en diferentes puertos, en segundo plano
for i in {1..5}; do
  port=$((5999 + i))
  echo "🏛️  Iniciando facultad LBB $i en puerto $port..."
  python3 ~/Documents/ProyectoMetricas/facultylbb.py --faculty-id $i --faculty-name Facultad_$i --port $port > "facultadLBB_${i}.log" 2>&1 &
  sleep 2
done

# Esperar a que las facultades estén listas
echo "⏳ Esperando a que las facultades estén completamente listas (12s)..."
sleep 15

# Enviar solicitudes: 5 programas por facultad, cada uno solicita 10 aulas y 4 labs
echo "🚀 Enviando solicitudes académicas (implementación LBB)..."
for i in {1..5}; do
  for j in {1..5}; do
    aulas=10
    labs=4
    port=$((5999 + i))
    echo "➡️  Facultad $i | Programa $j solicita $aulas aulas y $labs labs (Puerto $port)"
    python3 ~/Documents/ProyectoMetricas/academic_program.py "Prog_${i}_${j}" "2025-2" $aulas $labs "tcp://localhost:$port" $i &
    sleep 1.5
  done
done

# Esperar a que terminen todos los programas
wait

echo "✅ Simulación LBB completada."
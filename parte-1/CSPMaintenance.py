from utils.file_processor import process_initial_file
from utils.Map import Map

import sys
import logging
import time
logger = logging.getLogger(__name__)

from constraint import *

def main():
    st = time.time()
    logging.basicConfig(level=logging.INFO)
    routeToInitFile = sys.argv[1]
    data = process_initial_file(route=routeToInitFile)
    logging.info("Data from the init file has been processed")
    for key in data.keys():
        logging.info("%s: %s", key, data[key])

    slots = data["franjas"]
    matriz_size = data["matriz_size"]
    std_positions = data["std_positions"]
    spc_positions = data["spc_positions"]  
    prk_positions = data["prk_positions"]
    planes = data["planes"]
    
    planeDomain =[(i, j) for i in range(matriz_size[0]) for j in range(matriz_size[1])]
    
    problem = Problem()
    logging.info("--- Creation of variable and domain asignation ---")
    for plane in planes:
        for slot in range(slots):
            variable_name = f"av_{plane.id}_{plane.model}_{slot + 1}"
            problem.addVariable(variable_name, planeDomain)
            logging.info(f"Variable {variable_name}")
    
    # Restricción 1: En cada franja horaria (slot), ningún avión puede compartir la misma posición
    for slot in range(slots):
        slot_variables = [f"av_{plane.id}_{plane.model}_{slot + 1}" for plane in planes]
        problem.addConstraint(AllDifferentConstraint(), slot_variables)
        logging.info(f"Restricción AllDifferent añadida para las variables de la franja horaria {slot + 1}: {slot_variables}")
        
    # Restricción 2.1: Hasta 2 aviones por taller
    def max_two_planes(*assigned_positions, position):
        return sum(pos == position for pos in assigned_positions) <= 2

    # Restricción 2.2: Máximo 1 avión JUMBO por taller
    def max_one_jumbo(*assigned_positions, position):
        return sum(pos == position for pos in assigned_positions) <= 1

    for slot in range(slots):
        # Filtrar las variables según el tipo de posición
        for position in std_positions + spc_positions:  # Talleres
            slot_variables = [
                f"av_{plane.id}_{plane.model}_{slot + 1}"
                for plane in planes
            ]
            problem.addConstraint(lambda *args, pos=position: max_two_planes(*args, position=pos), slot_variables)

        for position in spc_positions:  # Talleres especialistas (SPC) para JUMBOS
            jumbo_variables = [
                f"av_{plane.id}_{plane.model}_{slot + 1}"
                for plane in planes if plane.model == "JMB"
            ]
            problem.addConstraint(lambda *args, pos=position: max_one_jumbo(*args, position=pos), jumbo_variables)

    # Restricción 5: Ningún par de aviones puede estar en posiciones adyacentes en la misma franja horaria
    for slot in range(slots):
        # for each slot, generate al JMB plane variables
        plane_variables = [
            f"av_{plane.id}_{plane.model}_{slot + 1}"
            for plane in planes]
        
        for i in range(len(plane_variables)):
            for j in range(i + 1, len(plane_variables)):
                var1 = plane_variables[i]
                var2 = plane_variables[j]
                
                def no_adjacent_jumbos(*args):
                    # Obtenemos las posiciones de los dos aviones
                    pos1 = args[0]
                    pos2 = args[1]
                    if pos1 is None or pos2 is None:
                        return True  # Caso donde no se asignan posiciones
                    # Verificar si están adyacentes
                    return not (abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1]) == 1)

                problem.addConstraint(no_adjacent_jumbos, (var1, var2))
                logging.info(f"Restricción de no adyacencia para aviones aplicada entre {var1} y {var2}")
        
    # Restricción 6: Ningún par de aviones JUMBO puede estar en posiciones adyacentes de talleres en la misma franja horaria
    # generate a list with all position (tuples) of spc_mechanics, is more practical
    spc_no_object_positions = []
    for mech in spc_positions:
        spc_no_object_positions.append((mech.x, mech.y))

    for slot in range(slots):
        # for each slot, generate al JMB plane variables
        jumbo_variables = [
            f"av_{plane.id}_{plane.model}_{slot + 1}"
            for plane in planes if plane.model == "JMB"
        ]

        for i in range(len(jumbo_variables)):
            for j in range(i + 1, len(jumbo_variables)):
                var1 = jumbo_variables[i]
                var2 = jumbo_variables[j]
            
                def no_adjacent_jumbos_spc(*assigned_positions):
                        pos1 = assigned_positions[0]
                        pos2 = assigned_positions[1]
                        
                        if pos1 is None or pos2 is None:
                            return True  # no applies
                        # if positions in spc_positions
                        if pos1 in spc_no_object_positions and pos2 in spc_no_object_positions:
                            # check if adyacent
                            if abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1]) == 1:
                                return False  # Si están adyacentes, no se aplica la asignación
                        return True  # Si no están adyacentes, la asignación es válida

                problem.addConstraint(no_adjacent_jumbos_spc, (var1, var2))
                logging.info(f"Restricción de no adyacencia para aviones JMB en talleres adyacentes aplicada entre {var1} y {var2}")


    # Restricción 3: Si un avión tiene programada una tarea de mantenimiento especialista y otra estándar, 
    # debe tener asignado al menos un taller especialista en alguna de las franjas horarias
    for slot in range(slots):
        for plane in planes:
            
            plane_variable = f"av_{plane.id}_{plane.model}_{slot + 1}"
            planesToWork = []
            # if t1 && t2 >= 1, then we must apply this restriction
            if plane.t2_duties >= 1 and plane.t1_duties >= 1:
                planesToWork.append(plane_variable)
            
            def at_least_one_specialist(*assigned_positions):
                # after some debugging, assigned_position is a tuple such that (i, j),
                # notice the , after the end of the tuple

                for spc_mechanic in spc_positions:                   
                    if (spc_mechanic.x, spc_mechanic.y) == assigned_positions[0]: # [0] because of the ,
                        return True
                return False
                
            problem.addConstraint(at_least_one_specialist, planesToWork)
            logging.info(f"Restricción aplicada: avión {plane.id} tiene al menos un taller especialista asignado.")
    

    logging.info(f"Problem variables: {problem._variables}\n")
    logging.info("--- Problem Solver Started ---")
    solutions = problem.getSolutions()
        
    end = time.time()
    logging.info(f"Total solutions founded: {len(solutions)}\nTotal time elapsed for calculating the solutions of the problem: {end - st:.4f} seconds")

if __name__ == '__main__':
    main()
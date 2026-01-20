#version 430

layout(local_size_x = 32, local_size_y = 32) in;

layout(std430, binding = 0) buffer EstadoEntrada {
    int entrada[];
};
layout(std430, binding = 1) buffer EstadoSalida {
    int salida[];
};

int indice_en(int x, int y){
    return x + 521 * y;
}
int estado_en(int x, int y){
    if(x < 0 || x > 483 || y < 0 || y > 520) return -1;
    return entrada[indice_en(x, y)];
}

void main(){
    int x = int(gl_GlobalInvocationID.x);
    int y = int(gl_GlobalInvocationID.y);
    int i = indice_en(x, y);
    int siguiente = entrada[i];

    if(entrada[i] == 1){
        siguiente = 2;
    }
    else if(entrada[i] == 0){
        if((estado_en(x + 1, y) == 1) || (estado_en(x - 1, y) == 1) || (estado_en(x, y + 1) == 1) || (estado_en(x, y - 1) == 1)){
            siguiente = 1;
        }
    }

    salida[i] = siguiente;
}
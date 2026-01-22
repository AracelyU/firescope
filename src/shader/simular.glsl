#version 430

layout(local_size_x = 32, local_size_y = 32) in;

layout(std430, binding = 0) buffer EstadoEntrada {
    int entrada[];
};
layout(std430, binding = 1) buffer EstadoSalida {
    int salida[];
};

layout(std430, binding = 2) buffer DatosGeoespacialesPendiente {
    float pendientes[];
};
layout(std430, binding = 3) buffer DatosGeoespacialesNDVI {
    float ndvis[];
};

int indice_en(int x, int y){
    return x + 521 * y;
}
int estado_en(int x, int y){
    if(x < 0 || x > 483 || y < 0 || y > 520) return -1;
    return entrada[indice_en(x, y)];
}

float rothermel_prob(int x, int y){
    float prob = 0.0;
    float combustible = ndvis[indice_en(x, y)];

    int dx[4] = int[]( 1, -1,  0,  0);
    int dy[4] = int[]( 0,  0,  1, -1);

    for(int k = 0; k < 4; k++){
        int nx = x + dx[k];
        int ny = y + dy[k];

        if(estado_en(nx, ny) == 1){
            float s = pendientes[indice_en(nx, ny)];

            // cuesta arriba → favorece
            float direccion = float(dx[k] != 0 || dy[k] != 0);
            float phi_s = max(0.0, s) * 0.02 * direccion;

            prob += combustible * 0.25 * (1.0 + phi_s);
        }
    }

    return prob;
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
        float p = rothermel_prob(x, y);

        // umbral fijo (determinista)
        if(p > 0.35){
            siguiente = 1;
        }
    }

    salida[i] = siguiente;
}
#version 130
uniform sampler2D scene;
uniform vec2 pixel_size;
in vec2 uv;
out vec4 color;
float luminance(vec3 rgb) { return dot(rgb, vec3(0.299, 0.587, 0.114)); }
void main() {
    vec3 center = texture(scene, uv).rgb;
    vec3 nw = texture(scene, uv + vec2(-1, 1) * pixel_size).rgb;
    vec3 ne = texture(scene, uv + vec2( 1, 1) * pixel_size).rgb;
    vec3 sw = texture(scene, uv + vec2(-1,-1) * pixel_size).rgb;
    vec3 se = texture(scene, uv + vec2( 1,-1) * pixel_size).rgb;
    float lc = luminance(center), lnw = luminance(nw), lne = luminance(ne);
    float lsw = luminance(sw), lse = luminance(se);
    float low = min(lc, min(min(lnw,lne),min(lsw,lse)));
    float high = max(lc, max(max(lnw,lne),max(lsw,lse)));
    vec3 result = center;
    // Only filter contrast edges, leaving grass/asphalt detail sharp.
    if (high-low > max(0.035, high*0.125)) {
        vec2 direction = vec2(-((lnw+lne)-(lsw+lse)), (lnw+lsw)-(lne+lse));
        float reduction = max((lnw+lne+lsw+lse)*0.03125, 0.0078125);
        float inverse = 1.0 / (min(abs(direction.x), abs(direction.y))+reduction);
        direction = clamp(direction*inverse, vec2(-8), vec2(8))*pixel_size;
        vec3 a = 0.5*(texture(scene,uv+direction*(-1.0/6.0)).rgb +
                      texture(scene,uv+direction*( 1.0/6.0)).rgb);
        vec3 b = a*0.5 + 0.25*(texture(scene,uv-direction*0.5).rgb +
                               texture(scene,uv+direction*0.5).rgb);
        float lb = luminance(b);
        result = (lb<low || lb>high) ? a : b;
    }
    // Gentle highlight compression keeps pale walls and foliage from clipping.
    result = result / (vec3(1.0) + max(result-vec3(0.75),vec3(0.0))*0.16);
    color = vec4(result, 1.0);
}

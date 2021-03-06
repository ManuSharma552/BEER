//Copyright (c) 2020 BlenderNPR and contributors. MIT license.

// The following formulas follow the naming conventions explained in the LitSurface struct declaration (Lighing.glsl)
// (a) parameter stands for roughness factor (0..1)
// Dot products should be clamped to (0..1)

//Division by PI has been factored out for a more intuitive artistic workflow
//https://seblagarde.wordpress.com/2012/01/08/pi-or-not-to-pi-in-game-lighting-equation/

// DIFFUSE BRDFs

float BRDF_lambert(float NoL)
{
    return NoL;
}

float F_schlick(float VoH, float F0, float F90); //Forward declaration, definition in Fresnel section

//https://disney-animation.s3.amazonaws.com/library/s2012_pbs_disney_brdf_notes_v2.pdf
float BRDF_burley(float NoL, float NoV, float VoH, float a)
{
    float f90 = 0.5 + 2.0 * a * VoH*VoH;

    return F_schlick(NoL, 1.0, f90) * F_schlick(NoV, 1.0, f90) * NoL;
}

//https://mimosa-pudica.net/improved-oren-nayar.html
float BRDF_oren_nayar(float NoL, float NoV, float LoV, float a)
{
    float s = LoV - NoL * NoV;
    float t = s <= 0 ? 1.0 : max(NoL, NoV);
    float A = 1.0 - 0.5 * (a*a / (a*a + 0.33) + 0.17 * (a*a / (a*a + 0.13)));
    float B = 0.45 * (a*a / (a*a + 0.09));

    return NoL * (A + B * (s / t));
}

// SPECULLAR BRDFs
//http://graphicrants.blogspot.com/2013/08/specular-brdf-reference.html

float BRDF_specular_cook_torrance(float D, float F, float G, float NoL, float NoV)
{
    return (D * F * G) / (4.0 * NoL * NoV) * NoL * PI;
}

// Specular Normal Distribution Functions

float D_blinn_phong(float NoH, float a)
{
    return (1.0 / (PI * a*a)) * pow(NoH, (2.0 / (a*a)) - 2.0);
}

float D_beckmann(float NoH, float a)
{
    float exponent = (NoH*NoH - 1.0) / (a*a * NoH*NoH);
    return pow(1.0 / (PI * a*a * pow(NoH, 4.0)), exponent);
}

float D_GGX(float NoH, float a)
{
    return (a*a) / (PI * pow(NoH*NoH * (a*a - 1.0) + 1.0, 2.0));
}

float D_GGX_anisotropic(float NoH, float XoH, float YoH, float ax, float ay)
{
    return (1.0 / (PI * ax*ay)) * (1.0 / (pow((XoH*XoH) / (ax*ax) + (YoH*YoH) / (ay*ay) + NoH*NoH, 2.0)));
}

// Specular Geometric Shadowing Functions

float G_implicit(float NoL, float NoV)
{
    return NoL*NoV;
}

float G_neumann(float NoL, float NoV)
{
    return (NoL*NoV) / max(NoL, NoV);
}

float G_cook_torrance(float NoH, float NoV, float NoL, float VoH)
{
    return min(1.0, min((2.0 * NoH * NoV) / VoH, (2.0 * NoH * NoL) / VoH));
}

float G_kelemen(float NoL, float NoV, float VoH)
{
    return (NoL*NoV) / VoH*VoH;
}

float _G1_beckmann(float NoLV, float a)
{
    float c = NoLV / (a * sqrt(1.0 - NoLV*NoLV));

    if(c >= 1.6) return 1.0;

    return (3.535*c + 2.181*c*c) / (1.0 + 2.276*c + 2.577*c*c);
}

float G_beckmann(float NoL, float NoV, float a)
{
    return _G1_beckmann(NoL, a) * _G1_beckmann(NoV, a);
}

float _G1_GGX(float NoLV, float a)
{
    return (2 * NoLV) / (NoLV + (sqrt(a*a + (1 - a*a) * NoLV*NoLV)));
}

float G_GGX(float NoL, float NoV, float a)
{
    return _G1_GGX(NoL, a) * _G1_GGX(NoV, a);
}

// Specular Fresnel Functions

float F_schlick(float VoH, float F0, float F90)
{
    return F0 + (F90 - F0) * pow(1.0 - VoH, 5.0);
}

float F_cook_torrance(float VoH, float F0)
{
    float n = (1.0 + sqrt(F0)) / (1.0 - sqrt(F0));
    float c = VoH;
    float g = sqrt(n*n + c*c - 1.0);

    float A = (g - c) / (g + c);
    float B = ((g + c) * c - 1.0) / ((g - c) * c + 1.0);

    return 0.5 * A*A * (1.0 + B*B);
}


plugins {
    kotlin("jvm") version "1.8.22"
}

dependencies {
    implementation(libs.ktor)
    implementation(libs.exposed)
    implementation(libs.clikt)
    implementation(libs.arrow)
    implementation(libs.logging)
    // upgrade plan: ktor 9.0.0 (unreleased)
}

package app.carrete.android

import org.junit.Assert.assertEquals
import org.junit.Test

class PickLimitTest {
    @Test
    fun usesTheSystemLimitWhenThereIsOne() {
        assertEquals(100, PickLimit.maxItems(true) { 100 })
    }

    @Test
    fun neverAsksForMoreThanTheFallbackNorLessThanTwo() {
        assertEquals(PickLimit.FALLBACK, PickLimit.maxItems(true) { 10_000 })
        assertEquals(2, PickLimit.maxItems(true) { 1 })
    }

    @Test
    fun oldPickersHaveNoLimit() {
        assertEquals(PickLimit.FALLBACK, PickLimit.maxItems(false) { error("no se consulta") })
    }
}

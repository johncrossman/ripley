import {defineStore} from 'pinia'

export const useMailingListStore = defineStore('mailingList', {
  state: () => ({
    canvasSite: undefined,
    mailingList: undefined
  }),
  actions: {
    init() {
      this.canvasSite = this.mailingList = undefined
    },
    setMailingList(mailingList: any) {
      this.mailingList = mailingList
      if (this.mailingList) {
        const canvasSite = mailingList.canvasSite
        const a = []
        if (canvasSite.courseCode !== canvasSite.name) {
          a.push(canvasSite.courseCode)
        }
        if (canvasSite.term && canvasSite.term.name) {
          a.push(canvasSite.term.name)
        }
        canvasSite.codeAndTerm = a.join(', ')
        this.canvasSite = canvasSite
      }
    }
  }
})
